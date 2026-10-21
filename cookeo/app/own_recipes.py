"""Private cloud copies of local recipes, scoped to the authenticated account."""
import hashlib
import json
import urllib.parse
from . import ugc
from .cloud import API, APPS, UA, CloudError, http, recipe_reference
from .recipes import normalize


def fingerprint(recipe):
    value=normalize({k:v for k,v in recipe.items() if k not in ('id','updated','schema_version')})
    # These fields are local UI metadata, not recipe content sent to the cooker.
    for key in ('cloud_id','notes','favorite','photo','author','visibility','personal_source_id'):value.pop(key,None)
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def scope(cloud):
    account=cloud.profile()['rcu']['rcuAccountId']
    return hashlib.sha256(json.dumps([account,cloud.selection()],sort_keys=True).encode()).hexdigest()


def binding_key(cloud,local_id):
    return scope(cloud)+':'+local_id


def identifier(value):
    return recipe_reference((value.get('identifier') or value.get('fid') or {}).get('functionalId'))


def verify_private(cloud,reference):
    current=ugc.read(cloud,reference)
    if current.get('privacyLevel')!='PRIVATE':
        # Contain an unexpected server default immediately, then fail closed.
        current['privacyLevel']='PRIVATE'
        ugc.request(cloud,'/v3/recipes/PRO/'+urllib.parse.quote(reference,safe='')+'?format=lite','PUT',current)
        if ugc.read(cloud,reference).get('privacyLevel')!='PRIVATE':
            raise CloudError('The server did not confirm private visibility. Do not share this recipe.')
        raise CloudError('The server changed visibility unexpectedly. It was restored to PRIVATE; inspect before retrying.')
    headers={'ApiKey':APPS[cloud.selection()['brand']]['api_key'],'DCP-Context':cloud.context()['context'],
             'User-Agent':UA,'Accept':'application/json','Content-Type':'application/json'}
    path=API+'/common-api/v3/recipes/PRO/'+urllib.parse.quote(reference,safe='')+'/?format=mobile'
    try:http(path,headers=headers)
    except CloudError as error:
        if str(error)!='SEB HTTP 404':raise CloudError('Could not verify anonymous access to the private recipe.') from None
    else:raise CloudError('The recipe is anonymously accessible; private upload was not confirmed.')
    return current


def verify_content(cloud,recipe,mobile):
    expected=ugc.payload(cloud,recipe)
    if mobile.get('title')!=expected['title'] or float((mobile.get('yield') or {}).get('quantity',-1))!=expected['yield']['quantity']:
        raise CloudError('Cloud title or servings do not match the local recipe.')
    for field in ('prepTime','cookingTime'):
        if (mobile.get('durations') or {}).get(field)!=expected['durations'][field]:raise CloudError('Cloud recipe times do not match.')
    ingredients=mobile.get('ingredients',[])
    if [i.get('applicationDescription') for i in ingredients]!=[i['applicationDescription'] for i in expected['ingredients']]:
        raise CloudError('Cloud ingredients do not match the local recipe.')
    actual_steps=mobile.get('steps',[])
    if len(actual_steps)!=len(expected['steps']):raise CloudError('The cloud did not preserve every recipe step.')
    ids=[(i.get('fid') or {}).get('functionalId') for i in ingredients]
    for actual,wanted in zip(actual_steps,expected['steps']):
        if actual.get('applicationDescription')!=wanted['applicationDescription']:raise CloudError('Cloud step instructions do not match.')
        actual_refs={(i.get('fid') or {}).get('functionalId') if isinstance(i,dict) else i for i in actual.get('ingredients',[])}
        wanted_refs={ids[int(i['fid']['functionalId'][2:])] for i in wanted['ingredients']}
        if actual_refs!=wanted_refs:raise CloudError('The cloud did not preserve ingredients assigned to a step.')
        operations=lambda step:[op for seq in step.get('sequences',[]) for op in seq.get('operations',[])]
        a,w=operations(actual),operations(wanted)
        if len(a)!=len(w):raise CloudError('The cloud did not preserve cooker operations.')
        for left,right in zip(a,w):
            params=lambda op:{p['commonKey']:float(p['value']) for p in op.get('parameters',[])}
            if (left.get('program') or {}).get('key')!=right['program']['key'] or params(left)!=params(right):
                raise CloudError('The cloud changed a cooker program or parameter.')


def save_private(cloud,recipe):
    local_id=recipe['id'];key=binding_key(cloud,local_id);links=cloud.store.get('own_recipe_links',{})
    previous=links.get(key);digest=fingerprint(recipe)
    if not previous:
        source=ugc.personal_source(cloud,recipe)
        original=(source.get('originalRecipe') or {}).get('fid') or source['fid']
        if any(link.get('original_reference')==original['functionalId'] for k,link in links.items() if k!=key and k.startswith(key.split(':',1)[0]+':')):
            raise ValueError('Pro tento základ už existuje jiný místní osobní recept. Zvol jiný základ, aby se nepřepsala jeho úprava.')
        ugc.payload(cloud,recipe)  # Validate all steps before recording an attempt.
        previous={'creation_pending':True,'original_reference':original['functionalId'],'verified':False}
        links[key]=previous;cloud.store.set('own_recipe_links',links)
        # Exactly the native app adaptation flow. No author record is created.
        created=ugc.create_personal(cloud,recipe,source);reference=identifier(created)
        previous={**previous,'creation_pending':False,'reference':reference,'root_reference':None}
        links[key]=previous;cloud.store.set('own_recipe_links',links)
    if previous.get('creation_pending') or not previous.get('reference'):
        raise ValueError('Výsledek předchozího vytvoření osobní kopie není ověřený. Další kopii automaticky nezakládám.')
    current=verify_private(cloud,previous['reference'])
    if current.get('status')!='PERSONAL':
        raise ValueError('Tento záznam nemá ověřenou osobní kopii PERSONAL. Autorský záznam nebudu znovu odesílat ke schvalování.')
    if previous.get('original_reference') and recipe.get('personal_source_id') and previous['original_reference']!=recipe['personal_source_id']:
        raise ValueError('Základ již uložené osobní kopie nelze změnit místním přepsáním ID.')
    if previous.get('fingerprint')==digest and previous.get('verified'):
        verify_content(cloud,recipe,cloud.recipe(previous['reference']))
        return {**previous,'local_id':local_id,'already_current':True,'photo_uploaded':False}
    previous['verified']=False;links[key]=previous;cloud.store.set('own_recipe_links',links)
    if previous.get('fingerprint'):ugc.update(cloud,previous['reference'],recipe)
    current=verify_private(cloud,previous['reference'])
    if current.get('status')!='PERSONAL':raise CloudError('The cloud did not preserve PERSONAL recipe status.')
    mobile=cloud.recipe(previous['reference']);verify_content(cloud,recipe,mobile)
    link={**previous,'grouping':recipe_reference((mobile.get('groupingId') or {}).get('functionalId')),
          'fingerprint':digest,'verified':True,'recipe_status':'PERSONAL','privacy':previous.get('privacy','PRIVATE')}
    links[key]=link;cloud.store.set('own_recipe_links',links)
    return {**link,'local_id':local_id,'already_current':False,'photo_uploaded':False}


def owned_link(cloud,local_id):
    return cloud.store.get('own_recipe_links',{}).get(binding_key(cloud,local_id))


def cloud_status(cloud,recipe):
    link=owned_link(cloud,recipe['id'])
    if not link:return {'uploaded':False,'privacy':None,'current':False}
    if not link.get('reference'):return {'uploaded':False,'privacy':None,'current':False,'creation_pending':True}
    root=ugc.read(cloud,link.get('root_reference') or link['reference'])
    personal=ugc.read(cloud,link['reference'])
    privacy=root.get('privacyLevel')
    if privacy not in ('PRIVATE','PUBLIC'):raise CloudError('Cloud visibility could not be verified.')
    result={**link,'uploaded':True,'privacy':privacy,
            'publication_status':root.get('status'),
            'personal_status':personal.get('status'),
            'publicly_published':privacy=='PUBLIC' and root.get('status') in ('PUBLISHED','VALIDATED_MARKET'),
            'current':bool(link.get('verified') and link.get('fingerprint')==fingerprint(recipe)
                           and personal.get('privacyLevel')=='PRIVATE' and personal.get('status')=='PERSONAL')}
    links=cloud.store.get('own_recipe_links',{});links[binding_key(cloud,recipe['id'])]={**link,'privacy':privacy,'publication_status':root.get('status')}
    cloud.store.set('own_recipe_links',links)
    return result


def change_visibility(cloud,recipe,visibility):
    if visibility not in ('PRIVATE','PUBLIC'):raise ValueError('Invalid recipe visibility.')
    if visibility=='PUBLIC' and not recipe.get('photo','').startswith('data:image/'):
        raise ValueError('Pro veřejné zveřejnění přidej vlastní fotografii pokrmu do formuláře receptu.')
    link=owned_link(cloud,recipe['id'])
    if not link:raise ValueError('Nejdřív ulož recept na cloud.')
    root=link.get('root_reference')
    # Public visibility belongs to the authored recipe. The device's PERSONAL
    # adaptation remains private, including when its source is published.
    verify_private(cloud,link['reference'])
    if visibility=='PUBLIC':
        submitted=ugc.publish_author(cloud,recipe,root)
        root=identifier(submitted) if not root else root
        link={**link,'root_reference':root}
        links=cloud.store.get('own_recipe_links',{});links[binding_key(cloud,recipe['id'])]=link
        cloud.store.set('own_recipe_links',links)
    elif root and ugc.read(cloud,root).get('privacyLevel')!=visibility:
        ugc.visibility(cloud,root,visibility)
    observed=ugc.read(cloud,root or link['reference']).get('privacyLevel')
    if observed!=visibility:raise CloudError('Cloud nepotvrdil změnu viditelnosti receptu.')
    links=cloud.store.get('own_recipe_links',{});links[binding_key(cloud,recipe['id'])]={**link,'privacy':observed}
    cloud.store.set('own_recipe_links',links)
    return cloud_status(cloud,recipe)


def save_cloud(cloud,recipe):
    visibility=recipe.get('visibility','PRIVATE')
    if visibility=='PUBLIC' and not recipe.get('photo','').startswith('data:image/'):
        raise ValueError('Pro veřejné zveřejnění přidej vlastní fotografii pokrmu do formuláře receptu.')
    # Never create or update author sources in the private-save path. A source
    # marked PRIVATE entered moderation in live use; anonymity checks alone did
    # not establish that the publication workflow was bypassed.
    result=save_private(cloud,recipe)
    if visibility=='PUBLIC':change_visibility(cloud,recipe,visibility)
    elif result.get('root_reference'):change_visibility(cloud,recipe,'PRIVATE')
    return cloud_status(cloud,recipe)


def sendable(cloud,recipe):
    result=cloud_status(cloud,recipe)
    if not result['uploaded'] or not result['current']:raise ValueError('Nejdřív ulož aktuální recept na cloud.')
    verify_private(cloud,result['reference'])
    verify_content(cloud,recipe,cloud.recipe(result['reference']))
    return result


def delete_cloud(cloud,recipe,*,all_scopes=False):
    links=cloud.store.get('own_recipe_links',{});key=binding_key(cloud,recipe['id'])
    if all_scopes and any(k.endswith(':'+recipe['id']) and k!=key for k in links):
        raise ValueError('Recept má kopii také pod jiným účtem nebo regionem. Nejdřív ji odstraň v daném profilu.')
    link=links.get(key)
    if not link:return {'deleted':True}
    # Only server-side ownership bindings qualify, never an imported cloud_id.
    refs=list(dict.fromkeys([link['reference'],link.get('root_reference')]))
    for ref in filter(None,refs):
        ugc.delete(cloud,ref)
    links=cloud.store.get('own_recipe_links',{});links.pop(key,None);cloud.store.set('own_recipe_links',links)
    return {'deleted':True}
