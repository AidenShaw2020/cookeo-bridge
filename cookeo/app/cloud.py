"""SEB client based on the supplied APK routes; never logs secrets or raw failures."""
import base64
import json
from pathlib import Path
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from .oauth import authorize_url,accept_redirect,SF_BASE

API='https://sebplatform.api.groupe-seb.com'
POOL='eu-west-1:f25c4598-48da-4fda-9c1a-27fe30bd2ffe'
BROKER='a1p8u39dc9ign8-ats.iot.eu-west-1.amazonaws.com'
UA='cookeat-android/36.0.0-RC3'
APPS=json.loads((Path(__file__).resolve().parents[1]/'resources/apps.json').read_text())


class CloudError(RuntimeError):pass


def http(url,*,method='GET',headers=None,body=None,form=None):
    headers=dict(headers or {})
    if form is not None:
        raw=urllib.parse.urlencode(form).encode();headers['Content-Type']='application/x-www-form-urlencoded'
    elif body is not None:
        raw=json.dumps(body).encode();headers['Content-Type']='application/json'
    else:raw=None
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    request=urllib.request.Request(url,raw,headers,method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=25) as response:
            data=response.read(8_000_001)
            if len(data)>8_000_000:raise CloudError('Odpověď překročila limit.')
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:raise CloudError('SEB HTTP '+str(error.code)) from None
    except (urllib.error.URLError,ValueError):raise CloudError('SEB nevrátil platnou odpověď.') from None


def expiry(token):
    try:
        value=token.split('.')[1]
        return float(json.loads(base64.urlsafe_b64decode(value+'='*(-len(value)%4)))['exp'])
    except (IndexError,ValueError,KeyError,TypeError):return 0


def safe_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value):
        raise ValueError('Neplatný identifikátor.')
    return value


def recipe_reference(value):
    if isinstance(value,str) and re.fullmatch(r'/v1/(?:recipes|variants)/[0-9]{1,16}/',value):return value
    return safe_id(value)


class Cloud:
    def __init__(self,store):
        self.store=store;self.lock=threading.RLock();self.cache={};self.pending=None

    def selection(self):
        return self.store.get('selection',{'brand':'moulinex','market':'BE','lang':'nl'})

    def configuration(self,brand=None):
        brand=brand or self.selection()['brand']
        if brand not in APPS:raise ValueError('Neplatná značka.')
        if brand not in self.cache:
            key=APPS[brand]['api_key']
            self.cache[brand]=http(API+'/common-api/v3/configurations/'+urllib.parse.quote(key,safe=''),
                headers={'ApiKey':key,'DCP-Context':brand,'User-Agent':UA})
        return self.cache[brand]

    def locales(self,brand):
        config=self.configuration(brand);out=[]
        for market in config.get('markets',[]):
            if market.get('rcuBrand')!=brand or market.get('rcuBaseUrl','').rstrip('/')!=SF_BASE:continue
            for locale in market.get('locales',[]):
                if locale.get('lang') and locale.get('rcuLang'):
                    out.append({'brand':brand,'market':market.get('rcuMarket'),
                                'lang':locale['lang'],'rcu_lang':locale['rcuLang'],
                                'context':market.get('profilePerimeter')})
        return out

    def context(self,selection=None):
        selected=selection or self.selection()
        match=next((c for c in self.locales(selected.get('brand')) if all(c[k]==selected.get(k)
                        for k in ('brand','market','lang'))),None)
        if not match:raise ValueError('Výrobce nepodporuje zvolenou zemi a jazyk.')
        return match

    def select(self,value):
        if not isinstance(value,dict) or set(value)!={'brand','market','lang'}:raise ValueError('Neplatné nastavení země.')
        context=self.context(value)
        if self.store.get('tokens') and value!=self.selection():
            raise ValueError('Před změnou země nebo značky nejdřív odpoj účet. Cloudový profil se tím nemaže.')
        self.store.set('selection',value)
        return context

    def start_login(self):
        context=self.context();client=self.configuration()['clientId']
        state=secrets.token_urlsafe(24);nonce=secrets.token_urlsafe(24)
        self.pending={'state':state,'nonce':nonce,'client':client,'context':context,'time':time.time()}
        return authorize_url(state,nonce,context['market'],context['rcu_lang'],client,context['brand'])

    def finish_login(self,redirect):
        p=self.pending
        if not p or time.time()-p['time']>600:raise ValueError('Přihlášení vypršelo. Otevři nový pokus.')
        tokens=accept_redirect(redirect,p['state'],p['nonce'],p['client'],p['context']['brand'])
        previous=self.store.get('tokens')
        self.store.set('tokens',tokens)
        try:result=self.profile()
        except Exception:
            self.store.set('tokens',previous);raise
        self.pending=None
        return result

    def tokens(self):
        with self.lock:
            tokens=self.store.get('tokens')
            if not tokens:raise CloudError('Nejdřív přihlas účet výrobce.')
            if tokens.get('profile_perimeter')!=self.selection()['brand']:
                raise CloudError('Relace patří jiné aplikaci.')
            client=self.configuration()['clientId']
            if tokens.get('client_id')!=client:raise CloudError('Relace patří jinému přihlašovacímu klientu.')
            if expiry(tokens.get('id_token',''))<=time.time()+30:
                data=http(SF_BASE+'/services/oauth2/token',method='POST',form={
                    'grant_type':'refresh_token','refresh_token':tokens['refresh_token'],'client_id':client})
                if not data.get('id_token') or not data.get('access_token'):raise CloudError('Přihlášení nelze obnovit.')
                tokens.update(id_token=data['id_token'],access_token=data['access_token'],
                              refresh_token=data.get('refresh_token') or tokens['refresh_token'])
                self.store.set('tokens',tokens)
            return tokens

    def request(self,path,method='GET',body=None):
        if not path.startswith('/common-api/') or '\\' in path:raise ValueError('Nepovolená cesta.')
        with self.lock:
            context=self.context();tokens=self.tokens()
            return http(API+path,method=method,body=body,headers={
                'ApiKey':APPS[context['brand']]['api_key'],'DCP-Context':context['context'],
                'Authorization':'Bearer '+tokens['access_token'],'Grant-Type':'RCUToken',
                'User-Agent':UA,'Accept':'application/json','Content-Type':'application/json'})

    def profile(self):
        profile=self.request('/common-api/profiles/me')
        if profile.get('profilePerimeter')!=self.context()['context']:raise CloudError('Profil neodpovídá nastavení.')
        account=(profile.get('rcu') or {}).get('rcuAccountId')
        if not isinstance(account,str) or not re.fullmatch(r'001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',account):
            raise CloudError('Profil neobsahuje ověřený účet.')
        name=profile.get('nickname')
        self.cache['account_name']=name.strip()[:100] if isinstance(name,str) else ''
        return profile

    def devices(self,profile=None):
        out=[]
        for p in ((profile or self.profile()).get('household') or {}).get('products') or []:
            iot=p.get('iot') or {}
            if iot.get('thingType') not in ('COO001','COO002'):continue
            try:identifier=str(uuid.UUID(iot['functionalId']))
            except (ValueError,KeyError,TypeError):continue
            out.append({'id':identifier,'thing_type':iot['thingType'],'name':p.get('name') or 'Cookeo',
                        'cmmf':str(p.get('cmmf') or ''),'appliance':p.get('appliance')})
        return out

    def search_recipes(self,query='',page=0,language=None):
        if not isinstance(query,str) or len(query)>200 or not isinstance(page,int) or not 0<=page<=10000:raise ValueError('Neplatné hledání.')
        query=query.strip()
        selection=self.selection()
        language=language or ''
        if language and not re.fullmatch('[a-z]{2}',language):raise ValueError('Invalid recipe language.')
        params=urllib.parse.urlencode({'market':'GS_'+selection['market'],
            **({'lang':language} if language else {}),
            'page':page,'size':24,'q':query,'groupBy':'topRecipe','myUniverse':'false','myOwnRecipe':'false','withAutomaticSpellcheck':'true'})
        body={'sort':{'name':'score' if query else 'creationDate','direction':'DESC'},
              'fieldList':['title','resourceMedias','creator','community','durations.totalTime','durations.prepTime','lang','topRecipe.id'],
              'fieldFilters':[{'field':'applianceGroups.reference.key','values':[self.appliance_group()],'type':'inclusion'},
                  {'field':'classifications.key_FOOD_COOKING','values':['IS_FOOD_COOKING'],'type':'exclusion'}]+(
                  [{'field':'lang.key','values':[language]}] if language else []),
              'facetList':[],'facetFilters':[],
              'nestedFieldFiltersGroup':[],'profileBasedFilters':{
              'filterApplianceGroup':True,'filterExcludedFoods':False,'filterKitchenwares':False},'ingredientSelected':[]}
        return self.request('/common-api/v4/search/recipes?'+params,'POST',body)

    def appliance_group(self,appliance='APPLIANCE_1232'):
        cache_key='appliances:'+json.dumps(self.selection(),sort_keys=True)
        if cache_key not in self.cache:
            s=self.selection()
            self.cache[cache_key]=self.request('/common-api/v2/sync/appliances/0/?'+urllib.parse.urlencode({'market':'GS_'+s['market'],'lang':s['lang']}))
        model=next((p for p in self.cache[cache_key].get('objects',[]) if p.get('id')==appliance),None)
        if not model or not model.get('connectable'):raise ValueError('Model není v katalogu připojitelný.')
        return safe_id((model.get('group') or {}).get('id'))

    def recipe(self,identifier,appliance_group=None):
        group=appliance_group or self.appliance_group()
        return self.request('/common-api/v3/recipes/PRO/'+urllib.parse.quote(recipe_reference(identifier),safe='')+'/?'+
                            urllib.parse.urlencode({'format':'mobile','applianceGroup':safe_id(group),
                                'status':'VALIDATED_MARKET,PUBLISHED,PERSONAL,VALIDATED_PARTNER'}))

    def recipe_comments(self,identifier,page=0):
        if not isinstance(page,int) or not 0<=page<=10000:raise ValueError('Invalid review page.')
        return self.request('/common-api/v2/recipes/PRO/'+urllib.parse.quote(recipe_reference(identifier),safe='')+
            '/comments?'+urllib.parse.urlencode({'withSiblings':'true','sortBy':'creationDate',
                'page':page,'size':10,'status':'PUBLISHED'}))

    def collections(self):
        s=self.selection()
        return self.request('/common-api/v4/collections?'+urllib.parse.urlencode({'lang':s['lang'],'market':'GS_'+s['market']}))

    def collection(self,identifier,action,value=None):
        identifier=safe_id(identifier) if identifier else None
        s=self.selection();query=urllib.parse.urlencode({'lang':s['lang'],'market':'GS_'+s['market']})
        base='/common-api/v4/collections'
        if action in ('create','rename'):
            name=value.get('name') if isinstance(value,dict) else None
            if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Název kuchařky musí mít 1–100 znaků.')
            return self.request(base+('?'+query if action=='create' else '/PRO/'+identifier),
                'POST' if action=='create' else 'PATCH',{'name':name.strip(),**({'recipes':[]} if action=='create' else {})})
        if action=='delete':return self.request(base+'/PRO/'+identifier,'DELETE')
        if action=='recipes':return self.request(base+'/PRO/'+identifier+'/recipes/search?'+query+'&page=0&size=100','POST',{'fieldList':['title'],
            'fieldFilters':[{'field':'lang.key','values':[s['lang']]},{'field':'market.key','values':['GS_'+s['market']]}]})
        recipe=recipe_reference(value.get('recipe_id'))
        if action=='add':return self.request(base+'/PRO/'+identifier+'/recipes?'+query,'POST',{'topRecipeId':recipe})
        if action=='remove':return self.request(base+'/PRO/'+identifier+'/recipes?'+query,'DELETE',{'topRecipeIds':[recipe]})
        raise ValueError('Neplatná operace s kuchařkou.')

    def device_code_url(self):
        context=self.context();tokens=self.tokens()
        expid=context['brand']+'000'+context['market']+'000'+context['rcu_lang']
        target=SF_BASE+'/devicecodeverification?'+urllib.parse.urlencode({'expid':expid})
        return SF_BASE+'/secur/frontdoor.jsp?'+urllib.parse.urlencode({'sid':tokens['access_token'],'retURL':target})

    def review(self,value):
        if not isinstance(value,dict):raise ValueError('Invalid review.')
        rating=value.get('rating');comment=value.get('text','')
        if type(rating) is not int or not 1<=rating<=5:raise ValueError('Select a rating from 1 to 5.')
        if not isinstance(comment,str) or len(comment)>4000:raise ValueError('Review text must contain at most 4000 characters.')
        identifier=recipe_reference(value.get('recipe_id'))
        recipe=self.recipe(identifier)
        identifier=recipe_reference((recipe.get('fid') or {}).get('functionalId'))
        base='/common-api/recipes/PRO/'+urllib.parse.quote(identifier,safe='')
        with self.lock:
            self.request(base+'/evaluations','POST',{'rating':str(float(rating))})
            result={'rating_sent':True,'comment_sent':False}
            if comment.strip():
                try:
                    self.request(base+'/comments','POST',{'content':comment.strip(),'status':'PENDING'})
                    result['comment_sent']=True
                except CloudError as error:result['comment_error']=str(error)
            return result

    def mqtt_connection(self,callback):
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
        from awscrt import auth,io
        from awsiot import mqtt_connection_builder
        with self.lock:
            profile=self.profile();tokens=self.tokens();config=self.configuration()
            if config['specificFields']['iotMQTTEndpoint']!=BROKER:raise CloudError('Neočekávaný broker.')
            ca=self.store.folder/'trusted-ca.pem'
            ca.write_text(''.join(ssl.DER_cert_to_PEM_cert(c) for c in ssl.create_default_context().get_ca_certs(binary_form=True)),encoding='ascii')
            client=boto3.client('cognito-identity',region_name='eu-west-1',verify=str(ca),
                config=Config(signature_version=UNSIGNED,retries={'max_attempts':0},connect_timeout=10,read_timeout=15))
            logins={'account.groupeseb.com':tokens['id_token']}
            identity=client.get_id(IdentityPoolId=POOL,Logins=logins)['IdentityId']
            credentials=client.get_credentials_for_identity(IdentityId=identity,Logins=logins)['Credentials']
            http('https://iot.api.groupe-seb.com/entity/v1/update',method='POST',body={
                'openIdToken':tokens['id_token'],'thingType':'COO002'},headers={
                'ApiKey':APPS[self.selection()['brand']]['api_key'],'User-Agent':UA})
            provider=auth.AwsCredentialsProvider.new_static(credentials['AccessKeyId'],credentials['SecretKey'],credentials['SessionToken'])
            loop=io.EventLoopGroup(1);resolver=io.DefaultHostResolver(loop);bootstrap=io.ClientBootstrap(loop,resolver)
            connection=mqtt_connection_builder.websockets_with_default_aws_signing(endpoint=BROKER,region='eu-west-1',
                credentials_provider=provider,client_bootstrap=bootstrap,ca_filepath=str(ca),
                client_id='mqtt-COO002-'+profile['rcu']['rcuAccountId']+'-'+secrets.token_hex(4),
                clean_session=True,keep_alive_secs=30,on_connection_interrupted=callback)
            try:connection.connect().result(timeout=20)
            except Exception:
                try:connection.disconnect().result(timeout=3)
                except Exception:pass
                raise CloudError('Připojení k IoT serveru se nezdařilo.') from None
            return connection,(loop,resolver,bootstrap,provider),credentials['Expiration'].timestamp()
