"""Evidence association regression checks, not a model accuracy benchmark."""
import copy
from datetime import date
from django.test import SimpleTestCase
from recruitment.schemas import ResumeOutput
from recruitment.services.evidence_service import validate_analysis
from recruitment.services.scoring_service import calculate
from .test_core import data, req, BLOCKS

class EvidenceAccuracyTests(SimpleTestCase):
    def validate(self, payload, blocks=BLOCKS, requirements=None):
        return validate_analysis(ResumeOutput.model_validate(payload), blocks, requirements or [req()], date(2026,10,4))

    def test_shorter_quote_in_same_project_passage_retains_strength(self):
        payload=data()
        payload['requirement_matches'][0]['source_refs'][0]['exact_quote']='Python API with tests'
        validated=self.validate(payload)
        self.assertEqual(validated['requirement_matches'][0]['evidence_level'],'strong')
        self.assertEqual(calculate([req()],validated)['overall'],100)

    def test_identical_quote_in_different_block_is_not_project_support(self):
        payload=data(); payload['requirement_matches'][0]['source_refs'][0]['block_id']='p1-b3'
        blocks=BLOCKS+[{'id':'p1-b3','text':BLOCKS[1]['text']}]
        validated=self.validate(payload,blocks)
        self.assertEqual(validated['requirement_matches'][0]['evidence_level'],'mentioned')

    def test_disjoint_passages_in_one_block_do_not_establish_support(self):
        payload=data()
        blocks=copy.deepcopy(BLOCKS);blocks[1]['text']='Built Python API with tests. Skills: Docker.'
        payload['requirement_matches'][0]['source_refs'][0]['exact_quote']='Skills: Docker.'
        validated=self.validate(payload,blocks,[req(key='docker')])
        self.assertEqual(validated['requirement_matches'][0]['evidence_level'],'mentioned')
        self.assertIn('mentioned only',validated['requirement_matches'][0]['explanation'])

    def test_substring_claim_support_retains_strength(self):
        payload=data(); ref={'block_id':'p1-b2','exact_quote':'Python API with tests'}
        payload['claims']=[{'id':'c1','text':'Python project','canonical_key':'python','source_refs':[ref], 'supporting_refs':[ref],'support_level':'strong','claimed_months':None,'relevant_experience_ids':[],'review_notes':[]}]
        self.assertEqual(self.validate(payload)['claims'][0]['support_level'],'strong')

    def test_grounding_still_rejects_invented_or_joined_quotes(self):
        for quote in ['Python API with excellent tests','Skills: Python, Django Built Python API with tests.']:
            payload=data();payload['requirement_matches'][0]['source_refs'][0]['exact_quote']=quote
            with self.assertRaises(ValueError):self.validate(payload)

    def test_project_evidence_outranks_repeated_skills_and_unrelated_content(self):
        strong=self.validate(data())
        payload=data();payload['candidate']['projects']=[]
        payload['requirement_matches'][0].update(source_refs=[{'block_id':'p1-b1','exact_quote':'Skills: Python, Django'}],relevant_project_ids=[])
        blocks=BLOCKS+[{'id':'p1-b3','text':'Marketing, accounting, bookkeeping, Python Python Python.'}]
        mentioned=self.validate(payload,blocks)
        self.assertEqual(calculate([req()],mentioned)['overall'],25)
        self.assertGreater(calculate([req()],strong)['overall'],calculate([req()],mentioned)['overall'])
        self.assertEqual(calculate([req()],mentioned)['essential_gaps'],1)

    def test_substring_credential_support_is_recognised(self):
        payload=data();payload['candidate']['education']=[{'description':'BSc Computer Science','source_refs':[{'block_id':'p1-b3','exact_quote':'Education: BSc Computer Science'}]}]
        payload['requirement_matches'][0].update(source_refs=[{'block_id':'p1-b3','exact_quote':'BSc Computer Science'}],relevant_project_ids=[])
        blocks=BLOCKS+[{'id':'p1-b3','text':'Education: BSc Computer Science'}]
        self.assertEqual(self.validate(payload,blocks,[req(category='education')])['requirement_matches'][0]['evidence_level'],'strong')
