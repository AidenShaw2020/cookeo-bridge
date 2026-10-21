import copy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import unittest
from aiohttp.test_utils import TestClient,TestServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cookeo'))
from app import ugc,own_recipes
from app.cloud import CloudError
from app.recipes import normalize
from app.store import Store
from app.server import make_app

def draft():
    return {'title':'Lifecycle test','steps':'A manual step','visibility':'PRIVATE'}

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.cloud=SimpleNamespace(store=self.store,profile=lambda:{'rcu':{'rcuAccountId':'TEST_ACCOUNT'}},
            selection=lambda:{'brand':'moulinex','market':'BE','lang':'nl'},context=lambda:{'context':'MOULINEX_BE'})
        self.recipe=self.store.put_recipe(draft());self.key=own_recipes.binding_key(self.cloud,self.recipe['id'])
        self.link={'reference':'OWN_PERSONAL','root_reference':'OWN_ROOT','grouping':'OWN_GROUP',
                   'verified':True,'fingerprint':own_recipes.fingerprint(self.recipe),'privacy':'PRIVATE'}
        self.store.set('own_recipe_links',{self.key:self.link})
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_new_recipe_defaults_private_and_rejects_unknown_visibility(self):
        value=draft();value.pop('visibility');self.assertEqual(normalize(value)['visibility'],'PRIVATE')
        with self.assertRaises(ValueError):normalize({**value,'visibility':'UNLISTED'})
    def test_visibility_is_separate_from_recipe_content(self):
        self.assertEqual(own_recipes.fingerprint(self.recipe),own_recipes.fingerprint({**self.recipe,'visibility':'PUBLIC'}))
    def test_public_toggle_is_blocked_before_any_cloud_write(self):
        with patch.object(ugc,'visibility') as write,patch.object(ugc,'read') as read:
            with self.assertRaises(ValueError):own_recipes.change_visibility(self.cloud,self.recipe,'PUBLIC')
        write.assert_not_called();read.assert_not_called()
        self.assertEqual(self.store.get('own_recipe_links')[self.key]['privacy'],'PRIVATE')
    def test_new_private_recipe_creates_only_personal_adaptation(self):
        self.store.set('own_recipe_links',{});self.cloud.recipe=lambda ref:{'groupingId':{'functionalId':'PUBLIC_SOURCE'}}
        source={'fid':{'functionalId':'PUBLIC_SOURCE','sourceSystem':'PRO','version':1}}
        with patch.object(ugc,'personal_source',return_value=source),patch.object(ugc,'payload',return_value={}),patch.object(ugc,'create_personal',return_value={'fid':{'functionalId':'NEW_PERSONAL'}}) as personal,patch.object(ugc,'publish_author') as author,patch('app.own_recipes.verify_private',return_value={'status':'PERSONAL'}),patch('app.own_recipes.verify_content'):
            result=own_recipes.save_private(self.cloud,self.recipe)
        author.assert_not_called();personal.assert_called_once_with(self.cloud,self.recipe,source)
        self.assertIsNone(result['root_reference']);self.assertEqual(result['original_reference'],'PUBLIC_SOURCE')
        self.assertEqual(result['recipe_status'],'PERSONAL');self.assertTrue(result['verified'])
    def test_lost_creation_response_does_not_repeat_post(self):
        self.store.set('own_recipe_links',{})
        with patch.object(ugc,'personal_source',return_value={'fid':{'functionalId':'PUBLIC_SOURCE'}}),patch.object(ugc,'payload',return_value={}),patch.object(ugc,'create_personal',side_effect=CloudError('Response lost')) as post:
            with self.assertRaises(CloudError):own_recipes.save_private(self.cloud,self.recipe)
            with self.assertRaises(ValueError):own_recipes.save_private(self.cloud,self.recipe)
        self.assertEqual(post.call_count,1);self.assertTrue(self.store.get('own_recipe_links')[self.key]['creation_pending'])
    def test_delete_never_deletes_unowned_personal_source(self):
        self.store.set('own_recipe_links',{self.key:{**self.link,'root_reference':None,'original_reference':'PUBLIC_SOURCE'}})
        with patch.object(ugc,'delete') as delete:own_recipes.delete_cloud(self.cloud,self.recipe)
        delete.assert_called_once_with(self.cloud,'OWN_PERSONAL')
    def test_existing_personal_save_does_not_write_the_moderated_author_source(self):
        self.cloud.recipe=lambda ref:{'groupingId':{'functionalId':'OWN_GROUP'}}
        def read(c,ref):return {'privacyLevel':'PRIVATE','status':'TO_BE_CORRECTED' if ref=='OWN_ROOT' else 'PERSONAL'}
        changed={**self.recipe,'title':'Updated private personal copy'}
        with patch.object(ugc,'read',side_effect=read),patch('app.own_recipes.http',side_effect=CloudError('SEB HTTP 404')),patch('app.own_recipes.verify_content'),patch.object(ugc,'update') as update,patch.object(ugc,'visibility') as visibility,patch.object(ugc,'publish_author') as create:
            result=own_recipes.save_cloud(self.cloud,changed)
        update.assert_called_once_with(self.cloud,'OWN_PERSONAL',changed)
        visibility.assert_not_called();create.assert_not_called()
        self.assertEqual(result['publication_status'],'TO_BE_CORRECTED')
        self.assertEqual(result['personal_status'],'PERSONAL');self.assertTrue(result['current'])
    def test_cloud_status_uses_observed_visibility_and_detects_unsaved_content(self):
        def read(c,ref):return {'privacyLevel':'PUBLIC'} if ref=='OWN_ROOT' else {'privacyLevel':'PRIVATE','status':'PERSONAL'}
        with patch.object(ugc,'read',side_effect=read):
            state=own_recipes.cloud_status(self.cloud,self.recipe)
            dirty=own_recipes.cloud_status(self.cloud,{**self.recipe,'title':'Changed title'})
        self.assertEqual(state['privacy'],'PUBLIC');self.assertTrue(state['current']);self.assertFalse(dirty['current'])
    def test_send_requires_current_cloud_copy_and_never_creates_one(self):
        with patch('app.own_recipes.cloud_status',return_value={'uploaded':True,'current':False}),patch.object(ugc,'publish_author') as create:
            with self.assertRaises(ValueError):own_recipes.sendable(self.cloud,self.recipe)
        create.assert_not_called()
    def test_delete_does_not_use_imported_cloud_reference(self):
        self.store.set('own_recipe_links',{})
        with patch.object(ugc,'delete') as delete:own_recipes.delete_cloud(self.cloud,{**self.recipe,'cloud_id':'SOMEONE_ELSE'})
        delete.assert_not_called()
    def test_partial_delete_keeps_links_for_retry(self):
        with patch.object(ugc,'delete',side_effect=[None,CloudError('403')]) as delete:
            with self.assertRaises(CloudError):own_recipes.delete_cloud(self.cloud,self.recipe)
        self.assertEqual([c.args[1] for c in delete.call_args_list],['OWN_PERSONAL','OWN_ROOT'])
        self.assertIn(self.key,self.store.get('own_recipe_links'));self.assertTrue(self.store.recipe(self.recipe['id']))
    def test_other_account_binding_prevents_false_complete_local_deletion(self):
        self.store.set('own_recipe_links',{self.key:self.link,'OTHER:'+self.recipe['id']:self.link})
        with patch.object(ugc,'delete') as delete:
            with self.assertRaises(ValueError):own_recipes.delete_cloud(self.cloud,self.recipe,all_scopes=True)
        delete.assert_not_called()
    def test_delete_404_is_only_success_after_read_confirms_gone(self):
        self.cloud.request=lambda *a,**k:None
        with patch.object(ugc,'read',side_effect=CloudError('SEB HTTP 404')):
            ugc.delete(self.cloud,'OWN_ROOT')
        with patch.object(ugc,'read',return_value={'title':'Still there'}):
            with self.assertRaises(CloudError):ugc.delete(self.cloud,'OWN_ROOT')
    def test_soft_delete_requires_mobile_404_and_sends_one_delete(self):
        self.cloud.request=Mock();self.cloud.recipe=Mock(side_effect=CloudError('SEB HTTP 404'))
        with patch.object(ugc,'read',side_effect=[{'status':'PERSONAL'},{'status':'DELETED'}]):
            ugc.delete(self.cloud,'OWN_PERSONAL')
        self.cloud.request.assert_called_once()
        self.assertEqual(self.cloud.request.call_args.kwargs['method'],'DELETE')
    def test_existing_tombstone_is_idempotent_without_another_delete(self):
        self.cloud.request=Mock();self.cloud.recipe=Mock(side_effect=CloudError('SEB HTTP 404'))
        with patch.object(ugc,'read',return_value={'status':'DELETED'}):ugc.delete(self.cloud,'OWN_PERSONAL')
        self.cloud.request.assert_not_called()
    def test_tombstone_with_readable_mobile_recipe_is_not_success(self):
        self.cloud.request=Mock();self.cloud.recipe=Mock(return_value={'title':'Still readable'})
        with patch.object(ugc,'read',return_value={'status':'DELETED'}):
            with self.assertRaises(CloudError):ugc.delete(self.cloud,'OWN_PERSONAL')
        self.cloud.request.assert_not_called()

class LifecycleHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=make_app(self.tmp.name)
        self.app.on_startup.clear();self.client=TestClient(TestServer(self.app));await self.client.start_server()
        self.store=self.app['store'];self.store.set('tokens',{'test':'not-a-real-token'})
        self.app['cloud'].cache['account_name']='TestOwner'
        self.headers={'Authorization':'Bearer '+self.store.get('admin_token'),'X-Cookeo-Request':'1'}
    async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
    async def test_author_is_assigned_on_server_not_trusted_from_form(self):
        response=await self.client.post('/api/library',json={**draft(),'author':'Impersonated'},headers=self.headers)
        self.assertEqual(response.status,201);self.assertEqual((await response.json())['author'],'TestOwner')
    async def test_failed_cloud_delete_keeps_local_copy_and_binding(self):
        recipe=self.store.put_recipe(draft());self.store.set('own_recipe_links',{'SCOPE:'+recipe['id']:{'reference':'OWN'}})
        with patch('app.server.delete_cloud',side_effect=CloudError('SEB HTTP 403')):
            response=await self.client.delete('/api/library/'+recipe['id'],headers=self.headers)
        self.assertEqual(response.status,502);self.assertTrue(self.store.recipe(recipe['id']))
        self.assertTrue(self.store.get('own_recipe_links'))
    async def test_missing_source_fails_before_creation_and_preserves_local_content(self):
        recipe=self.store.put_recipe(draft())
        with patch.object(self.app['cloud'],'profile',return_value={'rcu':{'rcuAccountId':'TEST_ACCOUNT'}}),patch.object(ugc,'publish_author') as create:
            response=await self.client.post('/api/library/'+recipe['id']+'/cloud',json={},headers=self.headers)
        self.assertEqual(response.status,400);create.assert_not_called();self.assertTrue(self.store.recipe(recipe['id']))
    async def test_send_route_does_not_save_cloud_implicitly(self):
        recipe=self.store.put_recipe(draft())
        with patch.object(self.app['service'],'transfer_state'),patch('app.server.sendable',side_effect=ValueError('Save first')),patch('app.server.save_cloud') as save:
            response=await self.client.post('/api/library/'+recipe['id']+'/send',json={},headers=self.headers)
        self.assertEqual(response.status,400);save.assert_not_called()
    async def test_pending_creation_is_not_reported_as_uploaded_in_library(self):
        recipe=self.store.put_recipe(draft())
        with patch.object(self.app['cloud'],'profile',return_value={'rcu':{'rcuAccountId':'TEST_ACCOUNT'}}):
            key=own_recipes.binding_key(self.app['cloud'],recipe['id'])
            self.store.set('own_recipe_links',{key:{'creation_pending':True,'verified':False}})
            response=await self.client.get('/api/library',headers=self.headers)
        state=(await response.json())['recipes'][0]['cloud_state']
        self.assertFalse(state['uploaded']);self.assertTrue(state['creation_pending'])

if __name__=='__main__':unittest.main()
