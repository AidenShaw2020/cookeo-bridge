import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cookeo'))
from app import ugc
from app.cloud import CloudError
from app.own_recipes import fingerprint,save_private,verify_private,binding_key,verify_content
from app.recipes import normalize
from app.store import Store


def recipe():
    return {'title':'Private test','servings':2,'prep_minutes':1,'cook_minutes':3,'course':'main',
            'ingredient_items':[{'name':'Water','quantity':'200','unit':'ml'}],
            'flow':[{'text':'Add water','action':'add','ingredient_indices':[0]},
                    {'text':'Cook','action':'pressure_low','duration_minutes':3,'ingredient_indices':[0]}]}


def programs():
    return {'PROGRAM_201857':{'parameterSettings':{'duration':{'key':'P_DURATION','name':{'key':'DURATION'},'bottomValue':60,'topValue':3600},
        'speed':{'key':'P_SPEED','name':{'key':'SPEED'},'bottomValue':0,'topValue':2,'defaultValue':0}}}}


class PrivateRecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.cloud=SimpleNamespace(store=self.store,profile=lambda:{'rcu':{'rcuAccountId':'ACCOUNT_A'}},
            selection=lambda:{'brand':'moulinex','market':'BE','lang':'nl'},context=lambda:{'context':'MOULINEX_BE'},
            appliance_group=lambda:'APPLIANCE_GROUP_3019')
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_create_uses_private_lite_contract_and_links_step_ingredients(self):
        with patch.object(ugc,'programs',return_value=programs()),patch.object(ugc,'request',return_value={}) as request:
            ugc.create(self.cloud,recipe())
        _,route,method,body=request.call_args.args
        self.assertEqual(route,'/v3/recipes?format=lite&sourceSystemKey=PRO')
        self.assertEqual(method,'POST');self.assertEqual(body['privacyLevel'],'PRIVATE')
        self.assertIsNone(body['ingredients'][0]['identifier'])
        self.assertEqual(body['steps'][1]['ingredients'],['##0'])
        op=body['steps'][1]['sequences'][0]['operations'][0]
        self.assertEqual(op['program'],'PROGRAM_201857')
        self.assertEqual(next(p['value'] for p in op['parameters'] if p['commonKey']=='DURATION'),'180')
    def test_program_constraints_reject_before_any_cloud_write(self):
        value=recipe();value['flow'][1]['duration_minutes']=100
        with patch.object(ugc,'programs',return_value=programs()),patch.object(ugc,'request') as request:
            with self.assertRaises(ValueError):ugc.create(self.cloud,value)
        request.assert_not_called()
    def test_personal_copy_keeps_private_visibility_and_owned_original(self):
        source={'fid':{'functionalId':'OUR_PRIVATE_ROOT','sourceSystem':'PRO'}}
        with patch.object(ugc,'programs',return_value=programs()),patch.object(ugc,'request',return_value={}) as request:
            ugc.create_personal(self.cloud,recipe(),source)
        _,route,method,body=request.call_args.args
        self.assertEqual(body['status'],'PERSONAL');self.assertEqual(body['privacyLevel'],{'key':'PRIVATE'})
        self.assertEqual(body['originalRecipe'],{'fid':source['fid']})
    def test_personal_update_preserves_status_and_real_ingredient_references(self):
        current={'status':'PERSONAL','ingredients':[{'identifier':'REAL_ING'}],'steps':[{'identifier':'S1'},{'identifier':'S2'}]}
        with patch.object(ugc,'programs',return_value=programs()),patch.object(ugc,'read',return_value=current),patch.object(ugc,'request',return_value={}) as request:
            ugc.update(self.cloud,'OUR_PERSONAL',recipe())
        body=request.call_args.args[3]
        self.assertEqual(body['status'],'PERSONAL');self.assertEqual(body['privacyLevel'],'PRIVATE')
        self.assertEqual(body['steps'][0]['ingredients'],['REAL_ING'])
    def test_anonymous_200_and_non404_errors_fail_closed(self):
        with patch.object(ugc,'read',return_value={'privacyLevel':'PRIVATE'}):
            for response in ({'title':'visible'},CloudError('SEB HTTP 403'),CloudError('SEB HTTP 500')):
                with patch('app.own_recipes.http',side_effect=response if isinstance(response,Exception) else None,return_value=response):
                    with self.assertRaises(CloudError):verify_private(self.cloud,'PRIVATE_TEST')
            with patch('app.own_recipes.http',side_effect=CloudError('SEB HTTP 404')) as http:
                verify_private(self.cloud,'PRIVATE_TEST')
                self.assertNotIn('Authorization',http.call_args.kwargs['headers'])
    def test_client_cloud_id_is_never_used_to_overwrite_original(self):
        local=self.store.put_recipe({**recipe(),'cloud_id':'SOMEONE_ELSES_RECIPE'})
        with patch.object(ugc,'create',return_value={'identifier':{'functionalId':'NEW_PRIVATE'}}) as create,patch.object(ugc,'update') as update,patch('app.own_recipes.verify_private',side_effect=CloudError('verify failed')):
            with self.assertRaises(CloudError):save_private(self.cloud,local)
        create.assert_called_once();update.assert_not_called()
        links=self.store.get('own_recipe_links');self.assertFalse(next(iter(links.values()))['verified'])
    def test_first_save_returns_personal_copy_not_private_author_draft(self):
        local=self.store.put_recipe({**recipe(),'cloud_id':'UNTRUSTED_ORIGINAL'})
        root={'fid':{'functionalId':'OUR_ROOT'},'groupingId':{'functionalId':'ROOT_GROUP'},'privacyLevel':{'key':'PRIVATE'}}
        personal={'fid':{'functionalId':'OUR_PERSONAL'},'groupingId':{'functionalId':'ROOT_GROUP'}}
        self.cloud.recipe=lambda ref: root if ref=='OUR_ROOT' else personal
        with patch.object(ugc,'create',return_value={'identifier':{'functionalId':'OUR_ROOT'}}),patch.object(ugc,'create_personal',return_value={'fid':{'functionalId':'OUR_PERSONAL'}}) as create_personal,patch('app.own_recipes.verify_private',return_value={'status':'PERSONAL'}),patch('app.own_recipes.verify_content'):
            result=save_private(self.cloud,local)
        self.assertEqual(result['reference'],'OUR_PERSONAL');self.assertEqual(result['root_reference'],'OUR_ROOT')
        self.assertEqual(result['recipe_status'],'PERSONAL');self.assertEqual(result['privacy'],'PRIVATE')
        self.assertIs(create_personal.call_args.args[2],root)
    def test_links_are_separate_for_accounts_and_regions(self):
        a=binding_key(self.cloud,'local-id')
        self.cloud.profile=lambda:{'rcu':{'rcuAccountId':'ACCOUNT_B'}}
        self.assertNotEqual(a,binding_key(self.cloud,'local-id'))
        self.cloud.profile=lambda:{'rcu':{'rcuAccountId':'ACCOUNT_A'}}
        self.cloud.selection=lambda:{'brand':'tefal','market':'CZ','lang':'cs'}
        self.assertNotEqual(a,binding_key(self.cloud,'local-id'))
    def test_local_edit_changes_fingerprint_but_favorite_does_not(self):
        a=recipe();b=copy.deepcopy(a);b['flow'][1]['duration_minutes']=4
        self.assertNotEqual(fingerprint(a),fingerprint(b))
        self.assertEqual(fingerprint(a),fingerprint({**a,'favorite':True,'notes':'Local note','photo':'','author':'Local name'}))
    def test_invalid_ingredient_references_cannot_be_saved(self):
        for indices in ([1],[-1],[True],[0,0]):
            value=recipe();value['flow'][0]['ingredient_indices']=indices
            with self.assertRaises(ValueError):normalize(value)
    def test_roundtrip_verification_rejects_changed_program_duration(self):
        with patch.object(ugc,'programs',return_value=programs()):
            expected=ugc.payload(self.cloud,recipe());mobile=copy.deepcopy(expected)
            mobile['yield']['quantity']=2
            mobile['ingredients'][0]['fid']['functionalId']='ingredient-real-id'
            for step in mobile['steps']:step['ingredients']=[{'fid':{'functionalId':'ingredient-real-id'}}]
            verify_content(self.cloud,recipe(),mobile)
            mobile['steps'][1]['sequences'][0]['operations'][0]['parameters'][0]['value']='999'
            with self.assertRaises(CloudError):verify_content(self.cloud,recipe(),mobile)


if __name__=='__main__':unittest.main()
