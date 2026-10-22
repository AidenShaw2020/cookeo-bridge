import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cookeo'))
from app.models import CookeoStatus, CookeoProgram
from app.programs import PROGRAM_NAMES, program_name
from app.service import DeviceState


class TelemetryTests(unittest.TestCase):
    def test_all_infinity_programs_have_both_languages(self):
        ids=[str(i) for i in range(201857,201881) if i!=201860]+['201937','20199']
        self.assertEqual(len(ids),25)
        for key in ids:
            for lang in ('en','cs'):
                self.assertTrue(PROGRAM_NAMES['PROGRAM_'+key][lang])
        self.assertEqual(program_name('PROGRAM_201858','Hoge druk','cs'),'Vysoký tlak')
        self.assertEqual(program_name('PROGRAM_201858','Hoge druk','en'),'High pressure')
        self.assertEqual(program_name('FUTURE','Future label','cs'),'Future label')

    def test_projection_uses_ui_language_and_exposes_duration(self):
        state=DeviceState({})
        state.receive('test/cookingStatus',{'currentStatus':'cooking','elapsedTime':120,
            'currentOperation':{'program':{'key':'PROGRAM_201858','name':'Hoge druk'},
                                'parameters':[{'type':'DURATION','value':'900'}]}})
        self.assertEqual(state.public('cs')['program'],'Vysoký tlak')
        self.assertEqual(state.public('en')['program'],'High pressure')
        self.assertEqual(state.public()['duration'],900)
        self.assertEqual(state.public()['remaining'],780)
        state.receive('test/cookingStatus',{'remainingTime':0})
        self.assertEqual(state.public()['remaining'],0)

    def test_warming_does_not_invent_a_countdown(self):
        status=CookeoStatus(current_status='warming',progress=40,elapsed_time=120,
            parameters=[{'type':'DURATION','value':'900'}])
        self.assertEqual(status.display_duration,900)
        self.assertIsNone(status.display_remaining_time)
        self.assertIsNone(CookeoStatus(current_status='warming',parameters=[]).display_duration)

    def test_new_phase_does_not_reuse_previous_countdown(self):
        status=CookeoStatus(current_status='cooking',remaining_time=600,elapsed_time=300,
            program=CookeoProgram('A','Old'),parameters=[{'type':'DURATION','value':'900'}])
        warming=status.merge(CookeoStatus(current_status='warming'))
        self.assertIsNone(warming.display_remaining_time)
        self.assertIsNone(warming.display_duration)
        self.assertIsNone(warming.program)
        idle=status.merge(CookeoStatus(current_status='idle'))
        self.assertIsNone(idle.display_duration)
        self.assertIsNone(idle.display_remaining_time)
        changed=status.merge(CookeoStatus(program=CookeoProgram('B','New')))
        self.assertIsNone(changed.display_duration)
        self.assertIsNone(changed.display_remaining_time)

    def test_parameters_survive_warmup_to_cooking_but_counters_do_not(self):
        status=CookeoStatus(current_status='warming',remaining_time=20,
            parameters=[{'type':'DURATION','value':'900'}])
        cooking=status.merge(CookeoStatus(current_status='cooking',elapsed_time=30))
        self.assertEqual(cooking.display_duration,900)
        self.assertEqual(cooking.display_remaining_time,870)
        partial=cooking.merge(CookeoStatus(elapsed_time=60))
        self.assertEqual(partial.display_remaining_time,840)
