import asyncio
import base64
from pathlib import Path
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
from aiohttp.test_utils import TestClient,TestServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cookeo'))
from app.store import Store
from app.server import make_app
from app.cloud import Cloud
from app.mqtt import discovery,Bridge
from app.service import DeviceState,Service
from app.pairing import prepare,Pairing
from app.oauth import authorize_url,accept_redirect
from urllib.parse import parse_qs,urlsplit


class CatalogSearchTests(unittest.TestCase):
    def test_grouping_and_model_filter_are_applied_before_pagination(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);cloud=Cloud(store)
            response={'content':[],'page':{'totalElements':49,'totalPages':3,'number':1}}
            with patch.object(cloud,'appliance_group',return_value='APPLIANCE_GROUP_3019'),patch.object(cloud,'request',return_value=response) as request:
                result=cloud.search_recipes('rice',page=1,language='cs')
            path,method,body=request.call_args.args
            query=parse_qs(urlsplit(path).query)
            self.assertEqual(query['groupBy'],['topRecipe'])
            self.assertEqual(query['page'],['1'])
            self.assertEqual(body['sort'],{'name':'score','direction':'DESC'})
            self.assertIn({'field':'lang.key','values':['cs']},body['fieldFilters'])
            self.assertIn({'field':'applianceGroups.reference.key','values':['APPLIANCE_GROUP_3019'],'type':'inclusion'},body['fieldFilters'])
            self.assertIn({'field':'classifications.key_FOOD_COOKING','values':['IS_FOOD_COOKING'],'type':'exclusion'},body['fieldFilters'])
            self.assertFalse(any(f['field']=='market.key' for f in body['fieldFilters']))
            self.assertIs(result,response)  # Keep the server's grouped totals and page boundaries.
            store.close()

    def test_blank_language_searches_across_languages_and_markets(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);cloud=Cloud(store)
            with patch.object(cloud,'appliance_group',return_value='APPLIANCE_GROUP_3019'),patch.object(cloud,'request',return_value={}) as request:
                cloud.search_recipes(page=846)
            path,method,body=request.call_args.args
            self.assertNotIn('lang',parse_qs(urlsplit(path).query))
            self.assertEqual(body['sort'],{'name':'creationDate','direction':'DESC'})
            self.assertFalse(any(f['field'] in ('lang.key','market.key') for f in body['fieldFilters']))
            store.close()

    def test_query_relevance_and_blank_browsing_order(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);cloud=Cloud(store)
            for query,normalized,sort in [(' kuře na paprice ','kuře na paprice','score'),('kure na paprice','kure na paprice','score'),('   ','','creationDate')]:
                with patch.object(cloud,'appliance_group',return_value='APPLIANCE_GROUP_3019'),patch.object(cloud,'request',return_value={}) as request:
                    cloud.search_recipes(query)
                path,method,body=request.call_args.args
                self.assertEqual(parse_qs(urlsplit(path).query,keep_blank_values=True)['q'],[normalized])
                self.assertEqual(body['sort']['name'],sort)
            store.close()

    def test_reviews_include_siblings_and_only_published_comments(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);cloud=Cloud(store)
            with patch.object(cloud,'request',return_value={'content':[]}) as request:
                cloud.recipe_comments('/v1/variants/123/',page=2)
            path=request.call_args.args[0];query=parse_qs(urlsplit(path).query)
            self.assertIn('%2Fv1%2Fvariants%2F123%2F',path)
            self.assertEqual(query['withSiblings'],['true'])
            self.assertEqual(query['status'],['PUBLISHED'])
            self.assertEqual(query['page'],['2'])
            self.assertEqual(query['size'],['10'])
            for bad in [-1,10001,1.5]:
                with self.assertRaises(ValueError):cloud.recipe_comments('123',bad)
            with self.assertRaises(ValueError):cloud.recipe_comments('../../private')
            store.close()


def device():
    return {'id':str(uuid.uuid4()),'name':'Test Cookeo','cmmf':'7211419888','thing_type':'COO002','appliance':'APPLIANCE_1232'}


class StorageTests(unittest.TestCase):
    def test_two_process_stores_do_not_erase_each_others_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            first=Store(folder);second=Store(folder)
            first.set('tokens',{'value':'one'});second.set('mqtt',{'host':'test'})
            first.set('selection',{'brand':'moulinex'})
            self.assertEqual(second.get('tokens'),{'value':'one'})
            self.assertEqual(first.get('mqtt'),{'host':'test'})
            first.close();second.close()
    def test_credentials_are_encrypted_and_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.set('tokens',{'refresh_token':'SYNTHETIC-SECRET'})
            self.assertNotIn(b'SYNTHETIC-SECRET',(Path(folder)/'settings.enc').read_bytes())
            store.close();store=Store(folder)
            self.assertEqual(store.get('tokens')['refresh_token'],'SYNTHETIC-SECRET');store.close()

    def test_library_crud_unicode_favorites_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            r=store.put_recipe({'title':'České rizoto','ingredients':'rýže','steps':'Uvařit.','favorite':True})
            self.assertTrue(store.all_recipes()[0]['favorite'])
            changed=store.put_recipe({'title':'Nové','steps':'Jiný postup.'},r['id'])
            self.assertEqual(changed['id'],r['id'])
            with self.assertRaises(ValueError):store.put_recipe({'title':'','steps':'x'})
            with self.assertRaises(ValueError):store.put_recipe({'title':'x','steps':'x','sql':'bad'})
            store.delete_recipe(r['id']);self.assertEqual(store.all_recipes(),[]);store.close()


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.app=make_app(self.folder.name,demo=True)
        self.client=TestClient(TestServer(self.app));await self.client.start_server()
        self.headers={'Host':'127.0.0.1','Authorization':'Bearer '+self.app['store'].get('admin_token'),'X-Cookeo-Request':'1'}
    async def asyncTearDown(self):await self.client.close();self.folder.cleanup()
    async def test_anonymous_api_and_rebinding_are_rejected(self):
        self.assertEqual((await self.client.get('/api/state',headers={'Host':'127.0.0.1'})).status,401)
        self.assertEqual((await self.client.get('/',headers={'Host':'evil.example'})).status,403)
    async def test_secret_values_never_in_settings_or_state(self):
        self.app['store'].set('mqtt',{'host':'local','password':'PRIVATE-PASSWORD'})
        for route in ('/api/settings','/api/state'):
            response=await self.client.get(route,headers=self.headers)
            self.assertEqual(response.status,200);self.assertNotIn('PRIVATE-PASSWORD',await response.text())
    async def test_csrf_and_missing_recipe_fields_rejected(self):
        headers={k:v for k,v in self.headers.items() if k!='X-Cookeo-Request'}
        self.assertEqual((await self.client.post('/api/library',headers=headers,json={'title':'a','steps':'b'})).status,403)
        self.assertEqual((await self.client.post('/api/library',headers=self.headers,json={'title':'a'})).status,400)
    async def test_demo_never_starts_cloud_pairing(self):
        with patch.object(self.app['pairing'],'start') as start:
            response=await self.client.post('/api/pairing/start',headers=self.headers,json={})
            self.assertEqual(response.status,400);start.assert_not_called()
    async def test_http_library_roundtrip_and_security_headers(self):
        response=await self.client.post('/api/library',headers=self.headers,json={'title':'Česky','steps':'Postup'})
        self.assertEqual(response.status,201);recipe=await response.json()
        self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')
        self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        response=await self.client.delete('/api/library/'+recipe['id'],headers=self.headers)
        self.assertEqual(response.status,204)


class ProtocolTests(unittest.TestCase):
    def test_mqtt_entities_have_no_commands_and_use_real_availability(self):
        configs=discovery(device());self.assertEqual(len(configs),12)
        for config in configs.values():self.assertNotIn('command_topic',config)
        config=next(v for k,v in configs.items() if '/remaining/' in k)
        self.assertEqual(config['device_class'],'duration');self.assertEqual(config['availability_mode'],'all')
    def test_idle_hides_stale_recipe_temperature_and_progress(self):
        state=DeviceState(device())
        state.receive('COO002/x/cookingStatus',{'currentStatus':'cooking','mode':'recipe','remainingTime':120,
            'currentRecipe':{'title':'Recipe','functionalId':'123'},'currentOperation':{'parameters':[{'type':'TEMPERATURE','value':'100'}]}})
        self.assertEqual(state.public()['remaining'],120)
        state.receive('COO002/x/cookingStatus',{'currentStatus':'idle'})
        self.assertIsNone(state.public()['remaining']);self.assertIsNone(state.public()['recipe'])
        self.assertIsNone(state.public()['temperature']);self.assertIsNone(state.public()['progress'])
    def test_older_cooking_event_does_not_replace_newer_version(self):
        state=DeviceState(device());state.receive('x/cookingStatus',{'version':10,'currentStatus':'done'})
        state.receive('x/cookingStatus',{'version':9,'currentStatus':'cooking'})
        self.assertEqual(state.public()['status'],'done')
    def test_oauth_preserves_rcu_case_and_rejects_invalid_language(self):
        url=authorize_url('state','nonce','BE','nlBE','client','moulinex')
        self.assertIn('moulinex000BE000nlBE',url)
        with self.assertRaises(ValueError):authorize_url('x','y','BE','nl/evil','client','moulinex')
        with self.assertRaises(ValueError):accept_redirect('gsmoduser://tokens#state=foreign','state','nonce','client','moulinex')


class SendTests(unittest.IsolatedAsyncioTestCase):
    async def test_recipe_payload_contains_only_selected_recipe_and_variant(self):
        from types import SimpleNamespace
        d=device();state=DeviceState(d);state.shadow.connected=True;state.source_connected=True
        state.receive('x/cookingStatus',{'currentStatus':'idle'})
        recipe={'groupingId':{'functionalId':'TOP_1'},'fid':{'functionalId':'VAR_1'},
                'applianceGroups':[{'key':'APPLIANCE_GROUP_3019'}]}
        cloud=SimpleNamespace(profile=lambda:{},devices=lambda p:[d],
            appliance_group=lambda p:'APPLIANCE_GROUP_3019',recipe=lambda *args:recipe)
        service=Service(cloud,Bridge());service.connected=True;service.states={d['id']:state};sent=[];loop=asyncio.get_running_loop()
        class Connection:
            def publish(self,topic,payload,qos):
                sent.append((topic,json.loads(payload)));state.receive('x/cookingStatus',{'currentRecipe':{'functionalId':'TOP_1'}})
                loop.call_soon_threadsafe(service.shadow_response,topic+'/accepted',{'clientToken':json.loads(payload)['clientToken']})
                return (SimpleNamespace(result=lambda timeout:None),0)
        service.connection=Connection()
        result=await service.send_recipe(d['id'],'VAR_1')
        self.assertTrue(result['device_confirmed']);self.assertEqual(len(sent),1)
        self.assertEqual(sent[0][1]['state'],{'desired':{'recipe':{'functionalId':'TOP_1','variant':{'functionalId':'VAR_1'}}}})
        self.assertTrue(result['cloud_accepted']);self.assertEqual(set(sent[0][1]),{'state','clientToken'})
    async def test_shadow_reply_must_match_request_token_and_topic(self):
        service=Service(None,Bridge());future=asyncio.get_running_loop().create_future()
        service.pending_recipe_updates['TOKEN']=('OWN/shadow/update',future)
        service.shadow_response('OTHER/shadow/update/accepted',{'clientToken':'TOKEN'})
        service.shadow_response('OWN/shadow/update/accepted',{'clientToken':'UNRELATED'})
        self.assertFalse(future.done())
        service.shadow_response('OWN/shadow/update/rejected',{'clientToken':'TOKEN','code':403})
        self.assertEqual(future.result(),{'accepted':False,'code':403})
    async def test_send_refuses_cooking_and_unowned_devices(self):
        from types import SimpleNamespace
        d=device();state=DeviceState(d);state.shadow.connected=True;state.status.current_status='cooking'
        service=Service(SimpleNamespace(),Bridge());service.connected=True;service.states={d['id']:state}
        with self.assertRaises(ValueError):await service.send_recipe(d['id'],'VAR_1')
        with self.assertRaises(ValueError):await service.send_recipe(str(uuid.uuid4()),'VAR_1')
    async def test_pairing_refuses_already_registered_device_before_ble(self):
        from types import SimpleNamespace
        cloud=SimpleNamespace(profile=lambda:{},devices=lambda p:[device()])
        pairing=Pairing(cloud,lambda:None)
        with patch('app.pairing.provision') as ble:
            with self.assertRaises(ValueError):await pairing.start({'use_ble':True})
            ble.assert_not_called()


if __name__=='__main__':unittest.main()

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_ha_proxy_discovery_auth_filter_and_no_gatt_writes(self):
        from aiohttp import web
        from app.discovery import ha_scan
        seen=[]
        async def socket(request):
            ws=web.WebSocketResponse();await ws.prepare(request)
            await ws.send_json({'type':'auth_required'})
            auth=await ws.receive_json();self.assertEqual(auth,{'type':'auth','access_token':'FAKE-ADMIN'})
            await ws.send_json({'type':'auth_ok'})
            subscribe=await ws.receive_json();seen.append(subscribe)
            await ws.send_json({'id':1,'type':'result','success':True,'result':None})
            await ws.send_json({'id':1,'type':'event','event':{'add':[
                {'address':'AA:BB:CC:DD:EE:FF','name':'SEB Cookeo','rssi':-44,'source':'proxy','connectable':True,'time':time.time()},
                {'address':'11:22:33:44:55:66','name':'Old device','time':time.time()-600},
                {'address':'bad','name':'invalid'}]}})
            async for message in ws:pass
            return ws
        app=web.Application();app.router.add_get('/api/websocket',socket)
        async with TestServer(app) as server:
            with tempfile.TemporaryDirectory() as folder:
                store=Store(folder);store.set('ha',{'url':str(server.make_url('')).rstrip('/'),'token':'FAKE-ADMIN'})
                with patch.dict('os.environ',{},clear=True):devices=await ha_scan(store,seconds=.1)
                self.assertEqual(len(devices),1);self.assertEqual(devices[0]['address'],'AA:BB:CC:DD:EE:FF')
                self.assertTrue(devices[0]['candidate']);store.close()
        self.assertEqual(seen,[{'id':1,'type':'bluetooth/subscribe_advertisements'}])
    async def test_missing_ha_configuration_has_clear_error(self):
        from app.discovery import ha_connection
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            with patch.dict('os.environ',{},clear=True):
                with self.assertRaises(ValueError):ha_connection(store)
            store.close()
    async def test_unknown_state_requires_explicit_idle_confirmation_and_blocks_cooking(self):
        from types import SimpleNamespace
        d=device();state=DeviceState(d);state.shadow.connected=True
        service=Service(SimpleNamespace(profile=lambda: {}),Bridge());service.connected=True;service.states={d['id']:state}
        with self.assertRaises(ValueError):await service.send_recipe(d['id'],'VAR_1')
        state.status.current_status='cooking'
        with self.assertRaises(ValueError):await service.send_recipe(d['id'],'VAR_1',confirm_idle=True)


class OptionsTests(unittest.TestCase):
    def test_addon_options_default_english_and_preserve_web_changes_on_restart(self):
        from app.options import apply_options
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);options={'brand':'moulinex','country':'BE','language':'nl','ui_language':'en'}
            (Path(folder)/'options.json').write_text(json.dumps(options))
            apply_options(store);self.assertEqual(store.get('ui_language'),'en')
            store.set('ui_language','cs');apply_options(store);self.assertEqual(store.get('ui_language'),'cs')
            store.set('tokens',{'fake':True});options['country']='FR';(Path(folder)/'options.json').write_text(json.dumps(options))
            apply_options(store);self.assertEqual(store.get('selection')['market'],'BE')
            self.assertTrue(store.get('configuration_error'));store.close()
