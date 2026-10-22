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
    for key in ('cloud_id','notes','favorite','photo','author','visibility','personal_source_id','recipe_kind','source_title','source_author'):value.pop(key,None)
    # Preserve ownership digests from v3; v4 adds provenance, not cooking data.
    value['schema_version']=3
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


def save_private(cloud,recipe,*,owned_original=None):
    local_id=recipe['id'];key=binding_key(cloud,local_id);links=cloud.store.get('own_recipe_links',{})
    previous=links.get(key);digest=fingerprint(recipe)
    if recipe.get('recipe_kind')=='authored' and owned_original is None:
        raise ValueError('Nový autorský recept odešli přes publikační formulář. Osobní úprava vzniká pouze importem online receptu.')
    if not previous or not previous.get('reference'):
        if previous and previous.get('creation_pending'):raise ValueError('Výsledek vytvoření osobní kopie není ověřený; další zápis se neopakuje.')
        source=owned_original or ugc.personal_source(cloud,recipe)
        original=(source.get('originalRecipe') or {}).get('fid') or source['fid']
        if any(link.get('original_reference')==original['functionalId'] for k,link in links.items() if k!=key and k.startswith(key.split(':',1)[0]+':')):
            raise ValueError('Pro tento originál už existuje osobní úprava v knihovně. Uprav tuto uloženou kopii.')
        ugc.payload(cloud,recipe)  # Validate all steps before recording an attempt.
        previous={**(previous or {}),'creation_pending':True,'original_reference':original['functionalId'],'verified':False,
                  'link_kind':'authored' if owned_original is not None else 'adaptation'}
        links[key]=previous;cloud.store.set('own_recipe_links',links)
        # Exactly the native app adaptation flow. No author record is created.
        created=ugc.create_personal(cloud,recipe,source);reference=identifier(created)
        previous={**previous,'creation_pending':False,'reference':reference,'root_reference':previous.get('root_reference')}
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


def author_fingerprint(recipe):
    return hashlib.sha256((fingerprint(recipe)+'|'+recipe.get('photo','')).encode()).hexdigest()


def cloud_status(cloud,recipe):
    link=owned_link(cloud,recipe['id'])
    if not link:return {'uploaded':False,'privacy':None,'current':False,'device_ready':False}
    root_ref=link.get('root_reference') or link.get('reference')
    if not root_ref:return {'uploaded':False,'privacy':None,'current':False,'device_ready':False,'creation_pending':True}
    root=ugc.read(cloud,root_ref)
    personal=ugc.read(cloud,link['reference']) if link.get('reference') else {}
    privacy=root.get('privacyLevel')
    if privacy=='COMMUNITY':privacy='PUBLIC'
    if privacy not in ('PRIVATE','PUBLIC'):raise CloudError('Cloud visibility could not be verified.')
    ready=bool(link.get('verified') and link.get('fingerprint')==fingerprint(recipe)
                and personal.get('privacyLevel')=='PRIVATE' and personal.get('status')=='PERSONAL')
    authored=link.get('link_kind')=='authored' or recipe.get('recipe_kind')=='authored' and bool(link.get('root_reference'))
    if authored:link={**link,'link_kind':'authored'}
    result={**link,'uploaded':True,'privacy':privacy,'publication_status':root.get('status'),
            'personal_status':personal.get('status'),'device_ready':ready,
            'publicly_published':privacy=='PUBLIC' and root.get('status') in ('PUBLISHED','VALIDATED_MARKET'),
            'current':link.get('author_fingerprint')==author_fingerprint(recipe) if authored else ready}
    links=cloud.store.get('own_recipe_links',{});links[binding_key(cloud,recipe['id'])]={**link,'privacy':privacy,'publication_status':root.get('status')}
    cloud.store.set('own_recipe_links',links)
    return result


def save_authored(cloud,recipe):
    errors=ugc.author_requirements(cloud,recipe)
    if errors:raise ValueError(' '.join(error['message'] for error in errors))
    key=binding_key(cloud,recipe['id']);links=cloud.store.get('own_recipe_links',{});link=links.get(key,{})
    if link and link.get('link_kind')!='authored':
        if link.get('root_reference') and not recipe.get('cloud_id') and not recipe.get('personal_source_id'):
            link={**link,'link_kind':'authored'}  # Legacy owned author binding.
        else:raise ValueError('Tento záznam je osobní úprava, nikoli samostatný autorský recept.')
    root=link.get('root_reference');digest=author_fingerprint(recipe)
    if link.get('root_creation_pending'):raise ValueError('Výsledek odeslání autorského receptu není ověřený; další záznam nezakládám.')
    if not root or link.get('author_fingerprint')!=digest:
        # Persist uncertainty before a new POST. A lost reply must not cause a
        # second public submission on retry. Existing roots are always updated.
        link={**link,'link_kind':'authored','root_creation_pending':False}
        links[key]=link;cloud.store.set('own_recipe_links',links)
        def creating():
            # Photo upload failure must remain retryable. Only the recipe POST
            # can create an uncertain new author record.
            link['root_creation_pending']=True
            links[key]=link;cloud.store.set('own_recipe_links',links)
        submitted=ugc.publish_author(cloud,recipe,root,before_create=creating)
        root=root or identifier(submitted)
        link={**link,'root_reference':root,'root_creation_pending':False}
        links[key]=link;cloud.store.set('own_recipe_links',links)
        observed=ugc.read(cloud,root)
        if observed.get('privacyLevel') not in ('PUBLIC','COMMUNITY'):raise CloudError('Výrobce nepotvrdil veřejné odeslání autorského receptu.')
        link.update(author_fingerprint=digest,privacy='PUBLIC',publication_status=observed.get('status'),
            grouping=recipe_reference((observed.get('groupingId') or observed.get('topRecipeId') or {}).get('functionalId')))
        links[key]=link;cloud.store.set('own_recipe_links',links)
    # Device delivery uses a separate private PERSONAL variant of OUR author
    # root, never an unrelated catalog base. Pending moderation is reported.
    if ugc.read(cloud,root).get('privacyLevel') not in ('PUBLIC','COMMUNITY'):
        ugc.visibility(cloud,root,'PUBLIC')
        if ugc.read(cloud,root).get('privacyLevel') not in ('PUBLIC','COMMUNITY'):raise CloudError('Výrobce nepotvrdil veřejné odeslání autorského receptu.')
    try:
        original=cloud.recipe(root)
        save_private(cloud,recipe,owned_original=original)
    except (CloudError,ValueError) as error:
        # Submission and device availability are independent outcomes. Keep the
        # confirmed author binding even if the private variant is not ready.
        result=cloud_status(cloud,recipe)
        return {**result,'device_copy_error':str(error)}
    return cloud_status(cloud,recipe)


def change_visibility(cloud,recipe,visibility):
    if visibility!='PRIVATE':raise ValueError('Veřejné odeslání potvrď v autorském publikačním formuláři.')
    link=owned_link(cloud,recipe['id'])
    if not link:raise ValueError('Nejdřív ulož recept na cloud.')
    if recipe.get('recipe_kind')=='adaptation':raise ValueError('Osobní úprava zůstává soukromá; veřejný autorský tok se na ni nepoužívá.')
    root=link.get('root_reference')
    if not root:raise ValueError('Recept nemá vlastní autorský záznam.')
    if ugc.read(cloud,root).get('privacyLevel')!='PRIVATE':ugc.visibility(cloud,root,'PRIVATE')
    if ugc.read(cloud,root).get('privacyLevel')!='PRIVATE':raise CloudError('Cloud nepotvrdil změnu viditelnosti receptu.')
    return cloud_status(cloud,recipe)


def save_cloud(cloud,recipe):
    if recipe.get('recipe_kind')=='authored':
        raise ValueError('Nový autorský recept odešli přes publikační formulář, nikoli jako soukromou osobní úpravu.')
    if recipe.get('visibility','PRIVATE')!='PRIVATE':raise ValueError('Importovaná osobní úprava se ukládá soukromě.')
    save_private(cloud,recipe)
    return cloud_status(cloud,recipe)


def sendable(cloud,recipe):
    result=cloud_status(cloud,recipe)
    if not result['uploaded'] or not result['current'] or not result.get('device_ready',result['current']):raise ValueError('Nejdřív ulož aktuální recept na cloud.')
    verify_private(cloud,result['reference'])
    verify_content(cloud,recipe,cloud.recipe(result['reference']))
    return result


def delete_cloud(cloud,recipe,*,all_scopes=False):
    links=cloud.store.get('own_recipe_links',{});key=binding_key(cloud,recipe['id'])
    if all_scopes and any(k.endswith(':'+recipe['id']) and k!=key for k in links):
        raise ValueError('Recept má kopii také pod jiným účtem nebo regionem. Nejdřív ji odstraň v daném profilu.')
    link=links.get(key)
    if not link:return {'deleted':True}
    if link.get('root_creation_pending') or link.get('creation_pending'):
        raise ValueError('Výsledek předchozího vytvoření není ověřený. Nejdřív je nutné dohledat cloudový záznam; místní recept a vazba zůstávají zachované.')
    # Only server-side ownership bindings qualify, never an imported cloud_id.
    refs=list(dict.fromkeys([link.get('reference'),link.get('root_reference')]))
    for ref in filter(None,refs):
        ugc.delete(cloud,ref)
    links=cloud.store.get('own_recipe_links',{});links.pop(key,None);cloud.store.set('own_recipe_links',links)
    return {'deleted':True}
