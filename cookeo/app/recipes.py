"""Versioned local recipe flows. Descriptions are not appliance commands."""
import math
import base64
import re
from urllib.parse import urlsplit

ACTIONS=('manual','prep','add','stir','wait','sear_strong','sear_medium','sear_gentle',
         'pressure_low','pressure_high','steam','simmer_low','simmer_medium','simmer_high',
         'bake','air_fry','keep_warm','serve','custom')
COURSES=('main','starter','soup','side','dessert','breakfast','snack','sauce','drink','other')
FIELDS={'title','ingredients','steps','notes','favorite','cloud_id','prep_minutes','cook_minutes',
        'servings','course','ingredient_items','flow','author','photo','visibility','personal_source_id',
        'recipe_kind','source_title','source_author'}


def minutes(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1440:
        raise ValueError('Duration must be between 0 and 1440 minutes.')
    return round(value,2)


def text(value,limit):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('Invalid recipe text length.')
    return value.strip()


def normalize(value):
    if not isinstance(value,dict) or set(value)-FIELDS:raise ValueError('Neplatná pole receptu.')
    result={k:text(value.get(k,''),limit) for k,limit in (('title',200),('notes',8000))}
    if not result['title']:raise ValueError('Vyplň název a postup.')
    result.update(prep_minutes=minutes(value.get('prep_minutes',0)),cook_minutes=minutes(value.get('cook_minutes',0)))
    servings=value.get('servings',4)
    if type(servings) is not int or not 1<=servings<=100:raise ValueError('Servings must be an integer between 1 and 100.')
    course=value.get('course','main')
    if course not in COURSES:raise ValueError('Invalid course.')
    result.update(servings=servings,course=course,favorite=bool(value.get('favorite',False)),schema_version=4)
    cloud=value.get('cloud_id')
    if cloud is not None and (not isinstance(cloud,str) or len(cloud)>128):raise ValueError('Neplatný cloudový recept.')
    result['cloud_id']=cloud
    source=value.get('personal_source_id')
    if source is not None and (not isinstance(source,str) or len(source)>128):raise ValueError('Invalid personal recipe source.')
    result['personal_source_id']=source
    kind=value.get('recipe_kind') or ('adaptation' if cloud or source else 'authored')
    if kind not in ('authored','adaptation'):raise ValueError('Invalid recipe kind.')
    if kind=='authored' and (cloud or source):raise ValueError('An imported recipe must retain its adaptation origin.')
    if kind=='adaptation' and not (cloud or source):raise ValueError('An adaptation needs its original recipe reference.')
    result.update(recipe_kind=kind,source_title=text(value.get('source_title',''),200),source_author=text(value.get('source_author',''),100))
    result['author']=text(value.get('author',''),100)
    visibility=value.get('visibility','PRIVATE')
    if visibility not in ('PRIVATE','PUBLIC'):raise ValueError('Invalid recipe visibility.')
    result['visibility']=visibility
    photo=value.get('photo','')
    if not isinstance(photo,str):raise ValueError('Invalid recipe photo.')
    if photo.startswith('data:'):
        match=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)',photo)
        if not match or len(photo)>750000:raise ValueError('Photo must be JPEG, PNG or WebP, at most 500 kB.')
        try:raw=base64.b64decode(match[2],validate=True)
        except ValueError:raise ValueError('Invalid photo data.') from None
        if len(raw)>500000 or not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'RIFF') and raw[8:12]==b'WEBP'):raise ValueError('Invalid photo format.')
    elif photo:
        url=urlsplit(photo)
        if len(photo)>2000 or url.scheme!='https' or not url.hostname or url.username or url.password:raise ValueError('Photo URL must use HTTPS.')
    result['photo']=photo
    items=value.get('ingredient_items')
    if items is None:
        items=[{'name':line,'quantity':'','unit':''} for line in text(value.get('ingredients',''),12000).splitlines() if line.strip()]
    if not isinstance(items,list) or len(items)>100:raise ValueError('Use at most 100 ingredient rows.')
    result['ingredient_items']=[]
    for item in items:
        if not isinstance(item,dict) or set(item)-{'name','quantity','unit'}:raise ValueError('Invalid ingredient row.')
        row={k:text(item.get(k,''),limit) for k,limit in (('name',250),('quantity',40),('unit',40))}
        if not row['name']:raise ValueError('Ingredient name is required.')
        result['ingredient_items'].append(row)
    result['ingredients']='\n'.join(' '.join(x[k] for k in ('quantity','unit','name') if x[k]) for x in result['ingredient_items'])
    flow=value.get('flow')
    if flow is None:
        flow=[{'text':line.strip(),'action':'manual','duration_minutes':0} for line in text(value.get('steps',''),24000).splitlines() if line.strip()]
    if not isinstance(flow,list) or not 1<=len(flow)<=80:raise ValueError('Add between 1 and 80 recipe steps.')
    result['flow']=[]
    for step in flow:
        if not isinstance(step,dict) or set(step)-{'text','action','duration_minutes','temperature_c','action_label','program_key','ingredient_indices','stirring_speed'}:raise ValueError('Invalid recipe step.')
        action=step.get('action','manual')
        if action not in ACTIONS:raise ValueError('Invalid cooker action.')
        description=text(step.get('text',''),4000)
        if not description and action=='manual':raise ValueError('Enter step instructions or select a cooker action.')
        row={'text':description,'action':action,'duration_minutes':minutes(step.get('duration_minutes',0)),
             'action_label':text(step.get('action_label',''),150),'program_key':text(step.get('program_key',''),80)}
        temperature=step.get('temperature_c')
        if temperature not in (None,''):
            if type(temperature) not in (int,float) or not math.isfinite(temperature) or not 0<=temperature<=250:raise ValueError('Invalid target temperature.')
            row['temperature_c']=temperature
        else:row['temperature_c']=None
        indices=step.get('ingredient_indices',[])
        if not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(result['ingredient_items']) for i in indices) or len(indices)!=len(set(indices)):
            raise ValueError('Invalid ingredient references in recipe step.')
        row['ingredient_indices']=indices
        speed=step.get('stirring_speed')
        if speed is not None and (type(speed) not in (int,float) or not math.isfinite(speed) or not 0<=speed<=10):raise ValueError('Invalid stirring speed.')
        row['stirring_speed']=speed
        result['flow'].append(row)
    result['steps']='\n\n'.join(f'{i+1}. '+(s['text'] or s['action_label'] or s['action']) for i,s in enumerate(result['flow']))
    return result


def migrate(value):
    if value.get('schema_version')==4:return value
    normalized=normalize({k:v for k,v in value.items() if k in FIELDS})
    return {**normalized,**{k:value[k] for k in ('id','updated') if k in value}}
