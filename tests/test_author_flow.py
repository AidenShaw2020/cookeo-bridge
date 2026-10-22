import sys,tempfile,unittest,copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from aiohttp.test_utils import TestClient,TestServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cookeo'))
from app import ugc,own_recipes
from app.cloud import CloudError
from app.recipes import normalize,migrate
from app.store import Store
from app.server import make_app


def authored():
    return {'title':'Author recipe','recipe_kind':'authored','photo':'data:image/jpeg;base64,/9j/2Q==',
        'prep_minutes':2,'cook_minutes':3,'servings':2,'course':'main',
        'ingredient_items':[{'name':'Water','quantity':'200','unit':'ml'}],
        'flow':[{'text':'Cook water','action':'pressure_low','duration_minutes':3,'ingredient_indices':[0]}]}

def program():
    return {'PROGRAM_201857':{'parameterSettings':{'duration':{'key':'D','name':{'key':'DURATION'},'bottomValue':60,'topValue':3600}}}}

class AuthorFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.cloud=SimpleNamespace(store=self.store,profile=lambda:{'rcu':{'rcuAccountId':'TEST_ACCOUNT'}},
            selection=lambda:{'brand':'moulinex','market':'BE','lang':'nl'},context=lambda:{'context':'MOULINEX_BE'},
            appliance_group=lambda:'APPLIANCE_GROUP_3019')
        self.recipe=self.store.put_recipe(authored());self.key=own_recipes.binding_key(self.cloud,self.recipe['id'])
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_origin_is_explicit_and_legacy_imports_migrate(self):
        self.assertEqual(normalize({'title':'New','steps':'Manual'})['recipe_kind'],'authored')
        old={'title':'Imported','steps':'Manual','cloud_id':'SOURCE','schema_version':3,'id':'local'}
        self.assertEqual(migrate(old)['recipe_kind'],'adaptation')
        with self.assertRaises(ValueError):normalize({**authored(),'cloud_id':'SOMEONE_ELSE'})
    def test_provenance_migration_keeps_existing_device_content_digest(self):
        import hashlib,json
        value=normalize(authored())
        for key in ('cloud_id','notes','favorite','photo','author','visibility','personal_source_id','recipe_kind','source_title','source_author'):value.pop(key,None)
        value['schema_version']=3
        legacy=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(own_recipes.fingerprint(authored()),legacy)
    def test_unsupported_author_title_and_missing_step_description_are_reported(self):
        value=authored();value['title']='Meal \U0001f372';value['flow'][0]['text']=''
        fields={error['field'] for error in ugc.author_requirements(self.cloud,value)}
        self.assertTrue({'title','flow'}<=fields)
    def test_personal_device_copy_retains_own_author_photo(self):
        original={'fid':{'functionalId':'OUR_AUTHOR'},'cover':{'media':{'key':'OWN_PHOTO'}},'resourceMedias':[{'media':{'key':'OWN_PHOTO'},'isCover':True}]}
        with patch.object(ugc,'programs',return_value=program()),patch.object(ugc,'request',return_value={}) as request:
            ugc.create_personal(self.cloud,authored(),original)
        value=request.call_args.args[3]
        self.assertEqual(value['cover'],original['cover']);self.assertEqual(value['privacyLevel'],{'key':'PRIVATE'})

    def test_author_form_checks_native_required_fields_before_any_write(self):
        value={**authored(),'photo':'','prep_minutes':0,'servings':100,'flow':[{'text':'Manual','action':'manual'}]}
        with patch.object(ugc,'request') as write:
            fields={e['field'] for e in ugc.author_requirements(self.cloud,value)}
        self.assertTrue({'photo','prep_minutes','servings','flow','ingredient_items'}<=fields);write.assert_not_called()
        with patch.object(ugc,'programs',return_value=program()):self.assertEqual(ugc.author_requirements(self.cloud,authored()),[])
    def test_an_import_cannot_enter_author_publication(self):
        value={**authored(),'recipe_kind':'adaptation','cloud_id':'SOURCE','source_title':'Original','source_author':'Other chef'}
        with patch.object(ugc,'http') as upload,patch.object(ugc,'request') as create:
            with self.assertRaises(ValueError):ugc.publish_author(self.cloud,value)
        upload.assert_not_called();create.assert_not_called()
    def test_author_draft_never_uses_private_catalog_adaptation_route(self):
        with patch.object(ugc,'personal_source') as source,patch.object(ugc,'publish_author') as publish:
            with self.assertRaises(ValueError):own_recipes.save_cloud(self.cloud,self.recipe)
        source.assert_not_called();publish.assert_not_called()
    def test_author_root_precedes_personal_device_copy_without_foreign_base(self):
        original={'fid':{'functionalId':'OUR_AUTHOR','sourceSystem':'PRO'},'title':'Author recipe'}
        self.cloud.recipe=Mock(return_value=original)
        def read(c,ref):
            return {'privacyLevel':'PRIVATE','status':'PERSONAL'} if ref=='OUR_PERSONAL' else {'privacyLevel':'PUBLIC','status':'VALIDATED_PARTNER','groupingId':{'functionalId':'OUR_GROUP'}}
        def save(c,recipe,*,owned_original):
            self.assertIs(owned_original,original)
            link=c.store.get('own_recipe_links')[self.key];self.assertEqual(link['root_reference'],'OUR_AUTHOR')
            link.update(reference='OUR_PERSONAL',verified=True,fingerprint=own_recipes.fingerprint(recipe),recipe_status='PERSONAL')
            c.store.set('own_recipe_links',{self.key:link});return link
        with patch.object(ugc,'author_requirements',return_value=[]),patch.object(ugc,'publish_author',return_value={'fid':{'functionalId':'OUR_AUTHOR'}}) as publish,patch.object(ugc,'read',side_effect=read),patch('app.own_recipes.save_private',side_effect=save),patch.object(ugc,'personal_source') as foreign:
            result=own_recipes.save_authored(self.cloud,self.recipe)
            own_recipes.save_authored(self.cloud,self.recipe)
        self.assertEqual(publish.call_count,1);self.assertEqual(publish.call_args.args,(self.cloud,self.recipe,None));foreign.assert_not_called()
        self.assertEqual(result['link_kind'],'authored');self.assertTrue(result['current']);self.assertTrue(result['device_ready']);self.assertFalse(result['publicly_published'])
    def test_lost_author_creation_is_not_automatically_repeated_or_forgotten(self):
        def lost(*args,**kwargs):
            kwargs['before_create']();raise CloudError('Lost reply')
        with patch.object(ugc,'author_requirements',return_value=[]),patch.object(ugc,'publish_author',side_effect=lost) as create:
            with self.assertRaises(CloudError):own_recipes.save_authored(self.cloud,self.recipe)
            with self.assertRaises(ValueError):own_recipes.save_authored(self.cloud,self.recipe)
        create.assert_called_once()
        with patch.object(ugc,'delete') as delete:
            with self.assertRaises(ValueError):own_recipes.delete_cloud(self.cloud,self.recipe)
        delete.assert_not_called();self.assertIn(self.key,self.store.get('own_recipe_links'))
    def test_failed_photo_upload_does_not_mark_uncertain_recipe_creation(self):
        with patch.object(ugc,'author_requirements',return_value=[]),patch.object(ugc,'publish_author',side_effect=CloudError('Photo upload failed')):
            with self.assertRaises(CloudError):own_recipes.save_authored(self.cloud,self.recipe)
        self.assertFalse(self.store.get('own_recipe_links')[self.key]['root_creation_pending'])

    def test_approved_community_author_visibility_is_recognized_as_public(self):
        self.store.set('own_recipe_links',{self.key:{'link_kind':'authored','root_reference':'OWN_AUTHOR','author_fingerprint':own_recipes.author_fingerprint(self.recipe)}})
        with patch.object(ugc,'read',return_value={'privacyLevel':'COMMUNITY','status':'VALIDATED_MARKET'}):
            result=own_recipes.cloud_status(self.cloud,self.recipe)
        self.assertTrue(result['publicly_published']);self.assertEqual(result['privacy'],'PUBLIC');self.assertFalse(result['device_ready'])

    def test_confirmed_submission_and_unavailable_device_copy_are_separate(self):
        self.cloud.recipe=Mock(side_effect=CloudError('SEB HTTP 404'))
        with patch.object(ugc,'author_requirements',return_value=[]),patch.object(ugc,'publish_author',return_value={'fid':{'functionalId':'OUR_AUTHOR'}}),patch.object(ugc,'read',return_value={'privacyLevel':'PUBLIC','status':'VALIDATED_PARTNER','groupingId':{'functionalId':'OUR_GROUP'}}):
            result=own_recipes.save_authored(self.cloud,self.recipe)
        self.assertTrue(result['uploaded']);self.assertTrue(result['current']);self.assertFalse(result['device_ready']);self.assertIn('device_copy_error',result)

class PublicationHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=make_app(self.tmp.name);self.app.on_startup.clear()
        self.client=TestClient(TestServer(self.app));await self.client.start_server();self.store=self.app['store']
        self.store.set('tokens',{'test':'not-real'});self.app['cloud'].cache['account_name']='Owner'
        self.headers={'Authorization':'Bearer '+self.store.get('admin_token'),'X-Cookeo-Request':'1'}
    async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
    async def test_review_is_read_only_and_submission_requires_confirmation(self):
        recipe=self.store.put_recipe(authored())
        with patch.object(ugc,'author_requirements',return_value=[{'field':'photo','message':'Photo required'}]),patch('app.server.save_authored') as save:
            response=await self.client.get('/api/library/'+recipe['id']+'/publication',headers=self.headers)
            self.assertEqual(response.status,200);self.assertFalse((await response.json())['valid'])
            response=await self.client.post('/api/library/'+recipe['id']+'/publication',headers=self.headers,json={})
        self.assertEqual(response.status,400);save.assert_not_called()
    async def test_confirmed_publication_persists_public_only_after_success(self):
        recipe=self.store.put_recipe(authored())
        with patch('app.server.save_authored',return_value={'uploaded':True,'privacy':'PUBLIC','publication_status':'VALIDATED_PARTNER'}):
            response=await self.client.post('/api/library/'+recipe['id']+'/publication',headers=self.headers,json={'confirm_publication':True})
        self.assertEqual(response.status,200);self.assertEqual(self.store.recipe(recipe['id'])['visibility'],'PUBLIC')
    async def test_import_origin_is_preserved_and_cannot_be_changed_to_authored(self):
        imported={**authored(),'recipe_kind':'adaptation','cloud_id':'SOURCE','source_title':'Original title','source_author':'Original chef'}
        response=await self.client.post('/api/library',json=imported,headers=self.headers);saved=await response.json()
        self.assertEqual(saved['author'],'Owner');self.assertEqual(saved['source_author'],'Original chef')
        response=await self.client.put('/api/library/'+saved['id'],json=authored(),headers=self.headers)
        self.assertEqual(response.status,400);self.assertEqual(self.store.recipe(saved['id'])['recipe_kind'],'adaptation')

if __name__=='__main__':unittest.main()
