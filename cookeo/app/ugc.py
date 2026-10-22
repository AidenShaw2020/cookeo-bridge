"""Native personal adaptations and explicit author-publication requests."""
import urllib.parse
import base64
import re
import secrets
import unicodedata
from .cloud import APPS, http, recipe_reference
from .recipes import normalize,FIELDS

API='https://sebplatform-direct.api.groupe-seb.com/common-api'
PROGRAMS={'sear_strong':'PROGRAM_201863','sear_medium':'PROGRAM_201862','sear_gentle':'PROGRAM_201867',
          'pressure_low':'PROGRAM_201857','pressure_high':'PROGRAM_201858','steam':'PROGRAM_201859',
          'simmer_low':'PROGRAM_201866','bake':'PROGRAM_201876','air_fry':'PROGRAM_201878','keep_warm':'PROGRAM_201871'}
COURSES={'main':'MAIN_COURSE','starter':'STARTER','side':'SIDE_DISH','dessert':'DESSERT'}


def request(cloud,path,method='GET',body=None):
    if not path.startswith('/') or '\\' in path or path.startswith('//'):raise ValueError('Invalid UGC route.')
    with cloud.lock:
        context=cloud.context();tokens=cloud.tokens()
        return http(API+path,method=method,body=body,headers={
            'ApiKey':APPS[context['brand']]['ugc_api_key'],'DCP-Context':context['context'],
            'Grant-Type':'RCUToken','Authorization':'Bearer '+tokens['access_token'],
            'Content-Type':'application/json','Accept':'application/json','User-Agent':'Mozilla/5.0'})


def programs(cloud):
    selection=cloud.selection();cache_key='ugc_programs:'+str(selection)
    if cache_key not in cloud.cache:
        query=urllib.parse.urlencode({'domain':'PRO_COO','market':'GS_'+selection['market'],'language':selection['lang']})
        data=request(cloud,'/references/programs?'+query)
        group=cloud.appliance_group()
        cloud.cache[cache_key]={k:v for k,v in data.items() if (v.get('applianceGroup') or {}).get('key')==group}
    return cloud.cache[cache_key]


def public_programs(cloud):
    selection=cloud.selection();out=[]
    for key,value in programs(cloud).items():
        name=value.get('name',{}).get('GS_'+selection['market'],{}).get(selection['lang'],key)
        out.append({'key':key,'name':name,'action':next((a for a,p in PROGRAMS.items() if p==key),'custom'),
                    'parameters':[{k:p.get(k) for k in ('key','bottomValue','topValue','defaultValue')}|
                        {'type':(p.get('name') or {}).get('key')} for p in value.get('parameterSettings',{}).values()]})
    return out


def payload(cloud,recipe):
    recipe=normalize({k:v for k,v in recipe.items() if k in FIELDS});selection=cloud.selection();group=cloud.appliance_group();available=programs(cloud)
    if recipe['course'] not in COURSES:raise ValueError('This model supports main course, starter, side dish and dessert in the online cookbook.')
    ingredients=[]
    for i,item in enumerate(recipe['ingredient_items']):
        description=' '.join(item[k] for k in ('quantity','unit','name') if item[k])
        quantity=None
        try:quantity=float(item['quantity'].replace(',','.')) if item['quantity'] else None
        except ValueError:pass
        ingredients.append({'fid':{'functionalId':'##'+str(i)},'applicationDescription':description,
            'applianceDescription':item['name'],'endFreeText':description,'quantity':quantity})
    if not ingredients:raise ValueError('Add at least one ingredient before saving online.')
    steps=[]
    for step in recipe['flow']:
        description=step['text'] or step['action_label'] or step['action']
        row={'applicationDescription':description,'applianceDescription':description,'useAppliance':False,
             'ingredients':[{'fid':{'functionalId':'##'+str(i)}} for i in step['ingredient_indices']],'ingredientsWithoutIdentifier':[],'programDuration':0,
             'manualDuration':round(step['duration_minutes']*60),'type':{'key':'PREPARATION'}}
        key=step['program_key'] or PROGRAMS.get(step['action'])
        if step['action'] in PROGRAMS or step['action']=='custom':
            if not key or key not in available:raise ValueError('Choose a supported cooker program for this step.')
            program=available[key];parameters=[];has_duration=False
            for param in program.get('parameterSettings',{}).values():
                kind=(param.get('name') or {}).get('key');value=None
                if kind=='DURATION':value=round(step['duration_minutes']*60);has_duration=True
                elif kind=='TEMPERATURE':value=step['temperature_c'] if step['temperature_c'] is not None else float(param['defaultValue'])
                elif kind=='SPEED':value=step['stirring_speed'] if step['stirring_speed'] is not None else float(param.get('defaultValue','0'))
                if value is None:continue
                if param.get('bottomValue') is not None and value<float(param['bottomValue']) or param.get('topValue') is not None and value>float(param['topValue']):raise ValueError('A step parameter is outside this cooker program\'s allowed range.')
                parameters.append({'key':param['key'],'commonKey':kind,'value':str(value)})
            if step['temperature_c'] is not None and not any(p['commonKey']=='TEMPERATURE' for p in parameters):raise ValueError('This cooker program does not accept a custom temperature.')
            if step['stirring_speed'] is not None and not any(p['commonKey']=='SPEED' for p in parameters):raise ValueError('This cooker program does not accept stirring speed.')
            row.update(useAppliance=True,type={'key':'COOKING'},programDuration=round(step['duration_minutes']*60) if has_duration else 0,
                sequences=[{'applianceGroup':{'key':group},'operations':[{'program':{'key':key},'parameters':parameters}]}])
            if has_duration:row['manualDuration']=0
        elif step['action'] in ('simmer_medium','simmer_high'):raise ValueError('Choose the simmering program supported by this cooker.')
        steps.append(row)
    return {'domain':{'key':'PRO_COO'},'market':'GS_'+selection['market'],'lang':selection['lang'],
        'title':recipe['title'],'shortTitle':recipe['title'][:80],'recipeType':{'key':'UGC'},'status':'PERSONAL','partner':{'key':'PARTNER_4'},
        'defaultApplianceGroup':{'key':group},'applianceGroups':[{'key':group}],
        'resourceMedias':[],'yield':{'quantity':recipe['servings'],'quantityDisplay':str(recipe['servings']),'unit':{'key':'UNIT_1'}},
        'durations':{'prepTime':recipe['prep_minutes'],'cookingTime':recipe['cook_minutes'],'offApplianceCookingTime':0,'restingTime':0},
        'ingredients':ingredients,'steps':steps,'kitchenwares':[],'courses':[{'key':COURSES[recipe['course']]}],
        'fullIngredients':'\n\n'.join(i['applicationDescription'] for i in ingredients),
        'instructions':[s['applicationDescription'] for s in steps],'fullInstructions':'\n\n'.join(s['applicationDescription'] for s in steps)}


def lite_payload(cloud,recipe):
    """Serialize the lite edit schema; creation privacy is not a workflow guard."""
    value=payload(cloud,recipe)
    for field in ('domain','recipeType','defaultApplianceGroup','partner'):
        value[field]=value[field]['key']
    value['applianceGroups']=[item['key'] for item in value['applianceGroups']]
    value['courses']=[item['key'] for item in value['courses']]
    value['yield']['unit']=value['yield']['unit']['key']
    value.update(privacyLevel='PRIVATE',status='VALIDATED_PARTNER')
    value['identifier']=None
    for ingredient in value['ingredients']:
        ingredient.pop('fid',None)
        # ##index belongs only in step references. New ingredient identifiers are
        # null in the manufacturer's editor; sending ##index here breaks remapping.
        ingredient['identifier']=None
        ingredient['endFreeText']=ingredient['applianceDescription']
        ingredient['unit']=''
    for step in value['steps']:
        step['type']=step['type']['key']
        step['ingredients']=[i['fid']['functionalId'] for i in step['ingredients']]
        step.pop('ingredientsWithoutIdentifier',None)
        for sequence in step.get('sequences',[]):
            sequence['applianceGroup']=sequence['applianceGroup']['key']
            for operation in sequence['operations']:
                operation['program']=operation['program']['key']
    return value


def read(cloud,identifier):
    return request(cloud,'/v3/recipes/PRO/'+urllib.parse.quote(recipe_reference(identifier),safe='')+'?format=lite')


def update(cloud,identifier,recipe):
    value=lite_payload(cloud,recipe)
    current=read(cloud,identifier)
    # PERSONAL is the device-readable personal adaptation, not an author draft.
    value['status']=current.get('status','VALIDATED_PARTNER')
    if current.get('originalRecipe'):value['originalRecipe']=current['originalRecipe']
    for field in ('ingredients','steps'):
        for index,item in enumerate(value[field]):
            old=(current.get(field) or [])
            if index<len(old):
                previous=old[index].get('identifier')
                if isinstance(previous,str) and previous and not previous.startswith('##'):item['identifier']=previous
    for step in value['steps']:
        step['ingredients']=[value['ingredients'][int(ref[2:])].get('identifier') or ref for ref in step['ingredients']]
    value['identifier']={'functionalId':recipe_reference(identifier),'sourceSystem':'PRO'}
    return request(cloud,'/v3/recipes/PRO/'+urllib.parse.quote(identifier,safe='')+'?format=lite','PUT',value)


def create_personal(cloud,recipe,original):
    value=payload(cloud,recipe)
    value.pop('partner',None)
    source=(original.get('originalRecipe') or {}).get('fid') or original['fid']
    value.update(originalRecipe={'fid':source},privacyLevel={'key':'PRIVATE'},
                 domain=original.get('domain') or value['domain'],market=original.get('market') or value['market'],lang=original.get('lang') or value['lang'])
    # Importing an existing recipe can retain its own cover. A newly authored
    # private recipe must not receive an unrelated source recipe's photograph.
    if recipe.get('recipe_kind')=='authored' or recipe.get('cloud_id')==original['fid']['functionalId']:
        if original.get('resourceMedias'):value['resourceMedias']=original['resourceMedias']
        if original.get('cover'):value['cover']=original['cover']
    return request(cloud,'/v3/recipes','POST',value)


def personal_source(cloud,recipe):
    """Use the app's adaptation flow, never create a private author draft."""
    ref=recipe.get('personal_source_id') or recipe.get('cloud_id')
    if not ref:raise ValueError('Vyber základ pro osobní kopii receptu, stejně jako v aplikaci výrobce.')
    group=cloud.appliance_group()
    original=cloud.recipe(ref)
    if not any(g.get('key')==group for g in original.get('applianceGroups',[])):
        raise ValueError('The original recipe is not compatible with this cooker.')
    if original.get('status') not in ('PUBLISHED','VALIDATED_MARKET') or (original.get('privacyLevel') or {}).get('key') not in ('PUBLIC','COMMUNITY'):
        raise ValueError('Jako základ zvol publikovaný katalogový recept, nikoli soukromý autorský záznam.')
    return original


def author_requirements(cloud,recipe):
    """Required fields observed in the manufacturer's author form; no writes."""
    recipe=normalize({k:v for k,v in recipe.items() if k in FIELDS});errors=[]
    def fail(field,message):errors.append({'field':field,'message':message})
    if recipe['recipe_kind']!='authored':fail('recipe_kind','Osobní úpravu nelze publikovat jako vlastní autorský recept.')
    def forbidden(value):return any(char!=' ' and unicodedata.category(char)[0] not in 'LMNP' for char in value)
    if forbidden(recipe['title']):fail('title','Název receptu nesmí obsahovat emoji ani jiné nepodporované znaky.')
    if not recipe['photo'].startswith('data:image/'):fail('photo','Přidej vlastní fotografii hotového pokrmu.')
    if recipe['prep_minutes']<1:fail('prep_minutes','Čas přípravy musí být alespoň 1 minuta.')
    if recipe['servings']>99:fail('servings','Výrobce přijímá nejvýše 99 porcí.')
    if recipe['course'] not in COURSES:fail('course','Vyber podporovaný typ jídla: hlavní chod, předkrm, příloha nebo dezert.')
    if not recipe['ingredient_items']:fail('ingredient_items','Přidej alespoň jednu surovinu.')
    used={i for step in recipe['flow'] for i in step['ingredient_indices']}
    if any(i not in used for i in range(len(recipe['ingredient_items']))):fail('ingredient_items','Přiřaď každou surovinu alespoň jednomu kroku.')
    for item in recipe['ingredient_items']:
        if forbidden(item['name']):fail('ingredient_items','Název suroviny nesmí obsahovat emoji ani jiné nepodporované znaky.')
        if item['quantity']:
            try:
                quantity=float(item['quantity'].replace(',','.'))
                if not 0<=quantity<=999:raise ValueError()
            except ValueError:fail('ingredient_items','Množství surovin musí být číslo od 0 do 999.')
    if any(not step['text'] or len(step['text'])>1000 for step in recipe['flow']):fail('flow','Každý krok potřebuje popis o délce nejvýše 1000 znaků.')
    if not any(step['program_key'] or step['action'] in PROGRAMS or step['action']=='custom' for step in recipe['flow']):
        fail('flow','Autorský recept musí obsahovat alespoň jeden program hrnce.')
    if not errors:
        try:payload(cloud,recipe)
        except ValueError as error:fail('flow',str(error))
    return errors


def publish_author(cloud,recipe,identifier=None,*,before_create=None):
    """Explicit public submission, matching the app's publication screen."""
    errors=author_requirements(cloud,recipe)
    if errors:raise ValueError(' '.join(e['message'] for e in errors))
    match=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)',recipe.get('photo',''))
    if not match:raise ValueError('Pro veřejné zveřejnění přidej vlastní fotografii pokrmu do formuláře receptu.')
    raw=base64.b64decode(match[2],validate=True)
    if len(raw)>500000:raise ValueError('Recipe photo is too large.')
    boundary='cookeo-'+secrets.token_hex(16)
    multipart=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="recipe.{match[1]}"\r\nContent-Type: image/{match[1]}\r\n\r\n').encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
    context=cloud.context();tokens=cloud.tokens()
    picture=http(API+'/statics/pictures/upload',method='POST',raw=multipart,headers={
        'ApiKey':APPS[context['brand']]['ugc_api_key'],'DCP-Context':context['context'],
        'Grant-Type':'RCUToken','Authorization':'Bearer '+tokens['access_token'],
        'Content-Type':'multipart/form-data; boundary='+boundary,'Accept':'application/json'})
    if not picture.get('key') or not picture.get('original'):raise ValueError('The manufacturer did not confirm the uploaded photo.')
    media={'media':{k:picture[k] for k in ('key','type','original','thumbnail','originalFilename','creationDate','releaseDate','isDisabled','metadata') if k in picture},'isCover':True}
    value=lite_payload(cloud,recipe);value.update(privacyLevel='PUBLIC',status='VALIDATED_PARTNER',resourceMedias=[media],cover=media)
    if identifier:
        current=read(cloud,identifier)
        for field in ('ingredients','steps'):
            for i,item in enumerate(value[field]):
                old=current.get(field,[])
                if i<len(old) and old[i].get('identifier'):item['identifier']=old[i]['identifier']
        for step in value['steps']:step['ingredients']=[value['ingredients'][int(ref[2:])].get('identifier') or ref for ref in step['ingredients']]
        value['identifier']={'functionalId':recipe_reference(identifier),'sourceSystem':'PRO'}
        return request(cloud,'/v3/recipes/PRO/'+urllib.parse.quote(identifier,safe='')+'?format=lite','PUT',value)
    if before_create:before_create()
    return request(cloud,'/v3/recipes?format=lite&sourceSystemKey=PRO','POST',value)


def visibility(cloud,identifier,privacy):
    if privacy not in ('PRIVATE','PUBLIC'):raise ValueError('Invalid recipe visibility.')
    value=read(cloud,identifier)
    value['privacyLevel']=privacy
    value['identifier']={'functionalId':recipe_reference(identifier),'sourceSystem':'PRO'}
    return request(cloud,'/v3/recipes/PRO/'+urllib.parse.quote(recipe_reference(identifier),safe='')+'?format=lite','PUT',value)


def delete(cloud,identifier):
    from .cloud import CloudError
    def soft_deleted(current):
        if current.get('status')!='DELETED':return False
        # The lite author API retains a tombstone. The mobile recipe endpoint
        # must also report 404 before local ownership bindings can be removed.
        try:cloud.recipe(identifier)
        except CloudError as error:
            if str(error)=='SEB HTTP 404':return True
            raise
        raise CloudError('Cloud nepotvrdil odstranění receptu. Místní kopie zůstává zachovaná.')
    try:current=read(cloud,identifier)
    except CloudError as error:
        if str(error)=='SEB HTTP 404':return
        raise
    if soft_deleted(current):return
    # Exact Android contract: ld0/d.java b(variantId, status).
    route='/common-api/v3/recipes/PRO/'+urllib.parse.quote(recipe_reference(identifier),safe='')+'/?'+urllib.parse.urlencode({'format':'mobile','status':current.get('status','PERSONAL')})
    try:cloud.request(route,method='DELETE')
    except CloudError as error:
        if str(error)!='SEB HTTP 404':raise CloudError('Cloud odmítl odstranění receptu. Místní kopie zůstává zachovaná. ('+str(error)+')') from None
    try:current=read(cloud,identifier)
    except CloudError as error:
        if str(error)=='SEB HTTP 404':return
        raise
    if soft_deleted(current):return
    raise CloudError('Cloud nepotvrdil odstranění receptu. Místní kopie zůstává zachovaná.')
