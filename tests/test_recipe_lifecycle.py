import copy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
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
            selection=lambda:{'brand':'moulinex','market':'BE','lang':'nl'})
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
    def test_public_toggle_changes_only_owned_root_and_verifies_personal_stays_private(self):
        with patch('app.own_recipes.verify_private') as private,patch.object(ugc,'visibility') as write,patch.object(ugc,'read',return_value={'privacyLevel':'PUBLIC'}),patch('app.own_recipes.cloud_status',return_value={'privacy':'PUBLIC'}):
            result=own_recipes.change_visibility(self.cloud,self.recipe,'PUBLIC')
        private.assert_called_once_with(self.cloud,'OWN_PERSONAL');write.assert_called_once_with(self.cloud,'OWN_ROOT','PUBLIC')
        self.assertEqual(result['privacy'],'PUBLIC');self.assertEqual(self.store.get('own_recipe_links')[self.key]['privacy'],'PUBLIC')
    def test_failed_public_toggle_does_not_record_false_success(self):
        with patch('app.own_recipes.verify_private'),patch.object(ugc,'visibility',side_effect=CloudError('SEB HTTP 403')):
            with self.assertRaises(CloudError):own_recipes.change_visibility(self.cloud,self.recipe,'PUBLIC')
        self.assertEqual(self.store.get('own_recipe_links')[self.key]['privacy'],'PRIVATE')
    def test_cloud_status_uses_observed_visibility_and_detects_unsaved_content(self):
        def read(c,ref):return {'privacyLevel':'PUBLIC'} if ref=='OWN_ROOT' else {'privacyLevel':'PRIVATE','status':'PERSONAL'}
        with patch.object(ugc,'read',side_effect=read):
            state=own_recipes.cloud_status(self.cloud,self.recipe)
            dirty=own_recipes.cloud_status(self.cloud,{**self.recipe,'title':'Changed title'})
        self.assertEqual(state['privacy'],'PUBLIC');self.assertTrue(state['current']);self.assertFalse(dirty['current'])
    def test_send_requires_current_cloud_copy_and_never_creates_one(self):
        with patch('app.own_recipes.cloud_status',return_value={'uploaded':True,'current':False}),patch.object(ugc,'create') as create:
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
    async def test_send_route_does_not_save_cloud_implicitly(self):
        recipe=self.store.put_recipe(draft())
        with patch.object(self.app['service'],'transfer_state'),patch('app.server.sendable',side_effect=ValueError('Save first')),patch('app.server.save_cloud') as save:
            response=await self.client.post('/api/library/'+recipe['id']+'/send',json={},headers=self.headers)
        self.assertEqual(response.status,400);save.assert_not_called()

if __name__=='__main__':unittest.main()
