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
    for key in ('cloud_id','notes','favorite','photo','author','visibility'):value.pop(key,None)
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
    root_reference=None
    if previous:
        current=verify_private(cloud,previous['reference'])
        personal=current.get('status')=='PERSONAL'
        if personal and previous.get('fingerprint')==digest and previous.get('verified'):
            verify_content(cloud,recipe,cloud.recipe(previous['reference']))
            return {**previous,'local_id':local_id,'already_current':True,'photo_uploaded':False}
        reference=previous['reference']
        root_reference=previous.get('root_reference') or (reference if not personal else None)
        # Mark stale before a write so interrupted updates cannot be sent as verified.
        previous['verified']=False;links[key]=previous;cloud.store.set('own_recipe_links',links)
        ugc.update(cloud,reference,recipe)
    else:
        result=ugc.create(cloud,recipe);reference=identifier(result)
        personal=False;root_reference=reference
        links[key]={'reference':reference,'root_reference':root_reference,'verified':False}
        cloud.store.set('own_recipe_links',links)
    verify_private(cloud,reference)
    mobile=cloud.recipe(reference)
    if (mobile.get('privacyLevel') or {}).get('key')!='PRIVATE':raise CloudError('Private mobile recipe was not confirmed.')
    verify_content(cloud,recipe,mobile)
    if not personal:
        # The cooker ignores private author drafts (VALIDATED_PARTNER). The
        # manufacturer's personalization flow creates a readable PERSONAL copy.
        created=ugc.create_personal(cloud,recipe,mobile);reference=identifier(created)
        links[key]={'reference':reference,'root_reference':root_reference,'verified':False}
        cloud.store.set('own_recipe_links',links)
        current=verify_private(cloud,reference)
        if current.get('status')!='PERSONAL':raise CloudError('The cloud did not create a PERSONAL recipe for the cooker.')
        mobile=cloud.recipe(reference);verify_content(cloud,recipe,mobile)
    elif verify_private(cloud,reference).get('status')!='PERSONAL':
        raise CloudError('The cloud did not preserve PERSONAL recipe status.')
    grouping=recipe_reference((mobile.get('groupingId') or {}).get('functionalId'))
    link={'reference':reference,'root_reference':root_reference,'grouping':grouping,
          'fingerprint':digest,'verified':True,'privacy':'PRIVATE','recipe_status':'PERSONAL'}
    links[key]=link;cloud.store.set('own_recipe_links',links)
    return {**link,'local_id':local_id,'already_current':False,'photo_uploaded':False}


def owned_link(cloud,local_id):
    return cloud.store.get('own_recipe_links',{}).get(binding_key(cloud,local_id))


def cloud_status(cloud,recipe):
    link=owned_link(cloud,recipe['id'])
    if not link:return {'uploaded':False,'privacy':None,'current':False}
    root=ugc.read(cloud,link.get('root_reference') or link['reference'])
    personal=ugc.read(cloud,link['reference'])
    privacy=root.get('privacyLevel')
    if privacy not in ('PRIVATE','PUBLIC'):raise CloudError('Cloud visibility could not be verified.')
    result={**link,'uploaded':True,'privacy':privacy,
            'current':bool(link.get('verified') and link.get('fingerprint')==fingerprint(recipe)
                           and personal.get('privacyLevel')=='PRIVATE' and personal.get('status')=='PERSONAL')}
    links=cloud.store.get('own_recipe_links',{});links[binding_key(cloud,recipe['id'])]={**link,'privacy':privacy}
    cloud.store.set('own_recipe_links',links)
    return result


def change_visibility(cloud,recipe,visibility):
    if visibility not in ('PRIVATE','PUBLIC'):raise ValueError('Invalid recipe visibility.')
    link=owned_link(cloud,recipe['id'])
    if not link:raise ValueError('Nejdřív ulož recept na cloud.')
    root=link.get('root_reference')
    if not root or root==link['reference']:raise ValueError('Nejdřív ulož recept na cloud v aktuálním formátu.')
    # Public visibility belongs to the authored recipe. The device's PERSONAL
    # adaptation remains private, including when its source is published.
    verify_private(cloud,link['reference'])
    ugc.visibility(cloud,root,visibility)
    observed=ugc.read(cloud,root).get('privacyLevel')
    if observed!=visibility:raise CloudError('Cloud nepotvrdil změnu viditelnosti receptu.')
    links=cloud.store.get('own_recipe_links',{});links[binding_key(cloud,recipe['id'])]={**link,'privacy':observed}
    cloud.store.set('own_recipe_links',links)
    return cloud_status(cloud,recipe)


def save_cloud(cloud,recipe):
    link=owned_link(cloud,recipe['id'])
    root=link and link.get('root_reference')
    dirty=not link or link.get('fingerprint')!=fingerprint(recipe) or not link.get('verified')
    if root and root!=link['reference'] and dirty:
        # Update the owned author source as well as the device-readable copy.
        # Editing first withdraws it; publication happens only after verification.
        links=cloud.store.get('own_recipe_links',{});links[binding_key(cloud,recipe['id'])]={**link,'verified':False}
        cloud.store.set('own_recipe_links',links)
        ugc.update(cloud,root,recipe)
        verify_private(cloud,root);verify_content(cloud,recipe,cloud.recipe(root))
    result=save_private(cloud,recipe)
    change_visibility(cloud,recipe,recipe.get('visibility','PRIVATE'))
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
