"""Same server for HA ingress, native development and Docker."""
import argparse
import asyncio
import contextlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import signal
import webbrowser
from aiohttp import web
from .cloud import Cloud,CloudError
from .mqtt import Bridge
from .pairing import Pairing
from .service import Service
from .store import Store
from .discovery import ha_scan, local_scan
from .options import apply_options
from .own_recipes import save_cloud,cloud_status,change_visibility,delete_cloud,sendable

ROOT=Path(__file__).parent


def make_app(folder,*,ingress=False,demo=False,allowed_hosts=None):
    store=Store(folder);cloud=Cloud(store);bridge=Bridge();service=Service(cloud,bridge)
    pairing=Pairing(cloud,service.changed)
    allowed_hosts=set(allowed_hosts or ('127.0.0.1','localhost'))
    @web.middleware
    async def security(request,handler):
        try:
            if ingress:
                if request.remote!='172.30.32.2' and not (request.path=='/health' and request.remote=='127.0.0.1'):raise web.HTTPForbidden()
            else:
                if request.url.host not in allowed_hosts:raise web.HTTPForbidden()
                if request.path.startswith('/api/') and not hmac.compare_digest(
                    request.headers.get('Authorization','').encode(),('Bearer '+store.get('admin_token')).encode()):
                    raise web.HTTPUnauthorized()
            if request.path.startswith('/api/') and request.method not in ('GET','HEAD'):
                if request.headers.get('X-Cookeo-Request')!='1':raise web.HTTPForbidden()
            response=await handler(request)
        except (ValueError,TypeError,KeyError) as error:
            response=web.json_response({'error':str(error) if type(error) is ValueError else 'Neplatný vstup nebo nenalezený záznam.'},status=400)
        except CloudError as error:response=web.json_response({'error':str(error)},status=502)
        except web.HTTPException as error:response=web.Response(status=error.status,text=error.text,headers=error.headers)
        except Exception as error:
            logging.getLogger('cookeo').warning('Požadavek skončil: %s',type(error).__name__)
            response=web.json_response({'error':'Operace se nezdařila ('+type(error).__name__+').'},status=500)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','X-Frame-Options':'SAMEORIGIN',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data: https:; object-src 'none'; base-uri 'none'; form-action 'self'"})
        return response
    app=web.Application(middlewares=[security],client_max_size=1_000_000)
    app['store']=store;app['cloud']=cloud;app['service']=service;app['pairing']=pairing;app['bridge']=bridge

    def require_live():
        if demo:raise ValueError('Ukázkový režim neprovádí cloudové operace.')

    async def page(request):return web.FileResponse(ROOT/'web/index.html')
    async def health(request):return web.json_response({'ok':True})
    async def state(request):
        result=service.public()
        if demo:
            result={'cloud_connected':False,'mqtt_connected':False,'last_error':None,'devices':[]}
        return web.json_response({**result,'demo':demo,'logged_in':bool(store.get('tokens')),
            'account_name':cloud.cache.get('account_name','') if store.get('tokens') else '',
            'new_cloud_recipes_enabled':True,'public_recipes_enabled':True,
            'selection':cloud.selection(),'pairing':pairing.public(),
            'recipe_count':len(store.all_recipes()),'recipe_transfer_supported':not demo,
            'ui_language':store.get('ui_language','en'),'ui_language':store.get('ui_language','en'),'ha_automatic':bool(os.environ.get('SUPERVISOR_TOKEN')),'configuration_error':store.get('configuration_error')})
    async def settings(request):
        if request.method=='GET':
            mqtt=store.get('mqtt',{})
            ha=store.get('ha',{})
            return web.json_response({'selection':cloud.selection(),'mqtt':{k:v for k,v in mqtt.items() if k!='password'},
                                     'mqtt_password_set':bool(mqtt.get('password')),
                                     'ha':{'url':ha.get('url',''),'token_set':bool(ha.get('token'))}})
        value=await request.json()
        if not isinstance(value,dict):raise ValueError('Neplatné nastavení.')
        if 'ui_language' in value:
            if value['ui_language'] not in ('en','cs'):raise ValueError('Unsupported interface language.')
            store.set('ui_language',value['ui_language'])
        if 'selection' in value:
            require_live();await asyncio.to_thread(cloud.select,value['selection'])
        if 'mqtt' in value:
            data=value['mqtt']
            if not isinstance(data,dict) or set(data)-{'host','port','username','password','tls'}:raise ValueError('Neplatné MQTT nastavení.')
            if not isinstance(data.get('host',''),str) or len(data.get('host',''))>253:raise ValueError('Neplatný MQTT server.')
            port=int(data.get('port',1883))
            if not 1<=port<=65535:raise ValueError('Neplatný MQTT port.')
            old=store.get('mqtt',{})
            if not data.get('password'):data['password']=old.get('password','')
            data['port']=port;data['tls']=bool(data.get('tls',False))
            store.set('mqtt',data)
            if not demo:await asyncio.to_thread(bridge.start,data)
        if 'ha' in value:
            data=value['ha']
            if not isinstance(data,dict) or set(data)-{'url','token'}:raise ValueError('Neplatné nastavení HA.')
            if not all(isinstance(v,str) for v in data.values()) or len(data.get('url',''))>500 or len(data.get('token',''))>8192:raise ValueError('Neplatná adresa nebo token HA.')
            data['token']=data.get('token') or store.get('ha',{}).get('token','')
            store.set('ha',data)
        return web.json_response({'ok':True})
    scan_lock=asyncio.Lock()
    async def bluetooth_scan(request):
        require_live()
        if scan_lock.locked():raise ValueError('Vyhledávání už běží. Počkej na jeho dokončení.')
        value=await request.json();source=value.get('source','ha' if ingress else 'local')
        if source not in ('local','ha'):raise ValueError('Neplatný zdroj Bluetooth.')
        async with scan_lock:
            devices=await (ha_scan(store) if source=='ha' else local_scan())
        return web.json_response({'source':source,'devices':devices})
    async def locales(request):
        require_live()
        return web.json_response({'locales':await asyncio.to_thread(cloud.locales,request.query.get('brand','moulinex'))})
    async def login(request):
        require_live()
        return web.json_response({'url':await asyncio.to_thread(cloud.start_login)})
    async def callback(request):
        require_live();value=await request.json()
        await asyncio.to_thread(cloud.finish_login,value.get('redirect',''))
        service.changed();return web.json_response({'ok':True})
    async def logout(request):
        require_live()
        if pairing.task and not pairing.task.done():raise ValueError('Nejdřív dokonči nebo zastav párování.')
        def clear():
            with cloud.lock:store.set('tokens',None)
        await asyncio.to_thread(clear);await service.disconnect();service.states={};bridge.register([]);service.changed()
        return web.json_response({'ok':True})
    async def refresh(request):
        require_live();service.changed();return web.json_response({'ok':True})
    async def library(request):
        if request.method=='GET':
            recipes=store.all_recipes()
            if store.get('tokens') and not demo:
                def cached_states():
                    from .own_recipes import scope,fingerprint
                    with cloud.lock:
                        prefix=scope(cloud)+':';links=store.get('own_recipe_links',{})
                        for recipe in recipes:
                            recipe['author']=cloud.cache.get('account_name',recipe.get('author',''))
                            link=links.get(prefix+recipe['id'])
                            recipe['cloud_state']=({'uploaded':True,'privacy':link.get('privacy'),
                                'publication_status':link.get('publication_status'),
                                'publicly_published':link.get('privacy')=='PUBLIC' and link.get('publication_status') in ('PUBLISHED','VALIDATED_MARKET'),
                                'personal_status':link.get('recipe_status'),
                                'current':bool(link.get('verified') and link.get('fingerprint')==fingerprint(recipe))}
                                if link and link.get('reference') else {'uploaded':False,'creation_pending':bool(link and link.get('creation_pending'))})
                try:await asyncio.to_thread(cached_states)
                except CloudError:pass  # The local library remains usable offline.
            return web.json_response({'format':'cookeo-library-v3','recipes':recipes})
        return web.json_response(await save_local(await request.json()),status=201)
    async def save_local(value,identifier=None):
        if not isinstance(value,dict):raise ValueError('Neplatný recept.')
        if store.get('tokens') and not demo:
            if not cloud.cache.get('account_name'):await asyncio.to_thread(cloud.profile)
            value['author']=cloud.cache.get('account_name','')
        else:value['author']=''
        return store.put_recipe(value,identifier)
    async def local_recipe(request):
        identifier=request.match_info['id']
        if request.method=='DELETE':
            if any(k.endswith(':'+identifier) for k in store.get('own_recipe_links',{})):
                await own_operation(identifier,lambda c,r:delete_cloud(c,r,all_scopes=True))
            store.delete_recipe(identifier);return web.Response(status=204)
        return web.json_response(await save_local(await request.json(),identifier))
    upload_lock=asyncio.Lock()
    async def own_operation(identifier,operation):
        require_live()
        async with upload_lock:
            def save():
                with cloud.lock:return operation(cloud,store.recipe(identifier))
            return await asyncio.to_thread(save)
    async def own_recipe_cloud(request):
        operation={'GET':cloud_status,'POST':save_cloud,'DELETE':delete_cloud}[request.method]
        result=await own_operation(request.match_info['id'],operation)
        return web.json_response(result)
    async def own_visibility(request):
        value=await request.json();identifier=request.match_info['id'];privacy=value.get('visibility')
        result=await own_operation(identifier,lambda c,r:change_visibility(c,r,privacy))
        recipe=store.recipe(identifier)
        from .recipes import FIELDS
        store.put_recipe({**{k:v for k,v in recipe.items() if k in FIELDS},'visibility':privacy},identifier)
        return web.json_response(result)
    async def own_recipe_send(request):
        value=await request.json()
        require_live()
        service.transfer_state(value.get('device_id'),value.get('confirm_idle') is True)
        result=await own_operation(request.match_info['id'],sendable)
        sent=await service.send_recipe(value.get('device_id'),result['reference'],value.get('confirm_idle') is True)
        return web.json_response({**sent,'privacy':result['privacy']})
    async def own_programs(request):
        require_live()
        from .ugc import public_programs
        return web.json_response({'programs':await asyncio.to_thread(public_programs,cloud)})
    async def own_sources(request):
        require_live()
        from .ugc import personal_sources
        return web.json_response(await asyncio.to_thread(personal_sources,cloud,request.query.get('q',''),int(request.query.get('page','0'))))
    async def search(request):
        require_live();data=await asyncio.to_thread(cloud.search_recipes,request.query.get('q',''),int(request.query.get('page','0')),request.query.get('lang'))
        return web.json_response(data)
    async def cloud_recipe(request):
        require_live();data=await asyncio.to_thread(cloud.recipe,request.match_info['id'])
        return web.json_response(data)
    async def recipe_comments(request):
        require_live()
        data=await asyncio.to_thread(cloud.recipe_comments,request.match_info['id'],int(request.query.get('page','0')))
        return web.json_response(data)
    async def send_recipe(request):
        require_live();value=await request.json()
        return web.json_response(await service.send_recipe(value.get('device_id'),value.get('recipe_id'),value.get('confirm_idle') is True))
    async def recipe_note(request):
        from .cloud import recipe_reference
        value=await request.json() if request.method=='PUT' else request.query
        identifier=recipe_reference(value.get('recipe_id'))
        key=json.dumps(cloud.selection(),sort_keys=True)+'|'+identifier
        return web.json_response({'note':store.recipe_note(key,value.get('note') if request.method=='PUT' else None)})
    async def review(request):
        require_live();value=await request.json()
        return web.json_response(await asyncio.to_thread(cloud.review,value))
    async def collections(request):
        require_live()
        if request.method=='POST':return web.json_response(await asyncio.to_thread(cloud.collection,None,'create',await request.json()),status=201)
        return web.json_response(await asyncio.to_thread(cloud.collections))
    async def collection(request):
        require_live();identifier=request.match_info['id'];action={'GET':'recipes','PATCH':'rename','DELETE':'delete'}[request.method]
        return web.json_response(await asyncio.to_thread(cloud.collection,identifier,action,await request.json() if request.method=='PATCH' else None))
    async def collection_recipe(request):
        require_live()
        return web.json_response(await asyncio.to_thread(cloud.collection,request.match_info['id'],
            'add' if request.method=='POST' else 'remove',await request.json()))
    async def pairing_start(request):
        require_live();await pairing.start(await request.json());return web.json_response(pairing.public(),status=202)
    async def pairing_approve(request):
        require_live()
        if pairing.state['phase']!='await_code':raise ValueError('Není otevřený krok s novým kódem.')
        pairing.approved.set();return web.json_response({'ok':True})
    async def pairing_page(request):
        require_live()
        if not pairing.page_available:raise ValueError('Nejdřív spusť párování.')
        return web.json_response({'url':await asyncio.to_thread(cloud.device_code_url)})
    async def pairing_cancel(request):
        pairing.cancelled.set();return web.json_response({'ok':True})
    async def startup(app):
        if not demo:
            bridge.start(store.get('mqtt',{}));service.start()
    async def cleanup(app):
        await pairing.stop();await service.stop();await asyncio.to_thread(bridge.stop);store.close()
    app.router.add_get('/',page);app.router.add_get('/health',health);app.router.add_static('/static',ROOT/'web')
    routes=[('GET','/api/state',state),('GET','/api/settings',settings),('POST','/api/settings',settings),
        ('GET','/api/locales',locales),('POST','/api/auth/start',login),('POST','/api/auth/finish',callback),
        ('POST','/api/auth/logout',logout),('POST','/api/refresh',refresh),('GET','/api/library',library),
        ('POST','/api/library',library),('PUT','/api/library/{id}',local_recipe),('DELETE','/api/library/{id}',local_recipe),
        ('GET','/api/library/{id}/cloud',own_recipe_cloud),('POST','/api/library/{id}/cloud',own_recipe_cloud),
        ('DELETE','/api/library/{id}/cloud',own_recipe_cloud),('PUT','/api/library/{id}/visibility',own_visibility),
        ('POST','/api/library/{id}/send',own_recipe_send),
        ('GET','/api/own-recipes/programs',own_programs),
        ('GET','/api/own-recipes/sources',own_sources),
        ('GET','/api/recipes/search',search),('GET','/api/recipes/{id}/comments',recipe_comments),
        ('GET','/api/recipes/{id}',cloud_recipe),('POST','/api/recipes/send',send_recipe),
        ('GET','/api/recipe-notes',recipe_note),('PUT','/api/recipe-notes',recipe_note),('POST','/api/recipes/review',review),
        ('GET','/api/collections',collections),('POST','/api/collections',collections),
        ('GET','/api/collections/{id}',collection),('PATCH','/api/collections/{id}',collection),('DELETE','/api/collections/{id}',collection),
        ('POST','/api/collections/{id}/recipes',collection_recipe),('DELETE','/api/collections/{id}/recipes',collection_recipe),
        ('POST','/api/pairing/start',pairing_start),('POST','/api/pairing/approve',pairing_approve),
        ('POST','/api/bluetooth/scan',bluetooth_scan),
        ('POST','/api/pairing/page',pairing_page),('POST','/api/pairing/cancel',pairing_cancel)]
    for method,path,handler in routes:app.router.add_route(method,path,handler)
    app.on_startup.append(startup);app.on_cleanup.append(cleanup)
    return app


async def serve(args):
    app=make_app(args.data,ingress=args.ingress,demo=args.demo,allowed_hosts=args.allow_host)
    if args.ingress:apply_options(app['store'])
    if args.ingress and not app['store'].get('mqtt'):
        options=Path(args.data)/'options.json'
        values=json.loads(options.read_text()) if options.exists() else {}
        preset={'host':values.get('mqtt_host',''),'port':values.get('mqtt_port',1883),
                'username':values.get('mqtt_username',''),'password':values.get('mqtt_password',''),'tls':values.get('mqtt_tls',False)}
        if not preset['host'] and os.environ.get('SUPERVISOR_TOKEN'):
            try:
                from .cloud import http
                result=await asyncio.to_thread(http,'http://supervisor/services/mqtt',
                    headers={'Authorization':'Bearer '+os.environ['SUPERVISOR_TOKEN']})
                data=result.get('data') or {}
                preset={k:data.get(k,v) for k,v in preset.items()}
            except Exception:pass
        if preset['host']:app['store'].set('mqtt',preset)
    runner=web.AppRunner(app,access_log=None)
    try:
        await runner.setup();await web.TCPSite(runner,args.bind,args.port).start()
        print('Cookeo web běží na portu '+str(args.port)+'.',flush=True)
        if args.open_browser and not args.ingress:
            webbrowser.open('http://127.0.0.1:'+str(args.port)+'/#token='+app['store'].get('admin_token'))
        stop=asyncio.Event()
        with contextlib.suppress(NotImplementedError,RuntimeError):
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM,stop.set)
        await stop.wait()
    finally:await runner.cleanup()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',default='/data' if Path('/data/options.json').exists() else '.dev-data')
    parser.add_argument('--bind',default='127.0.0.1');parser.add_argument('--port',type=int,default=8098)
    parser.add_argument('--ingress',action='store_true');parser.add_argument('--open-browser',action='store_true')
    parser.add_argument('--demo',action='store_true');parser.add_argument('--allow-host',action='append')
    args=parser.parse_args()
    logging.basicConfig(level=logging.WARNING,format='%(name)s: %(message)s')
    try:asyncio.run(serve(args))
    except KeyboardInterrupt:pass


if __name__=='__main__':main()
