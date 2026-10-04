import copy, json
from datetime import date
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, TestCase
from recruitment.schemas import ResumeOutput
from recruitment.services import providers
from recruitment.services.evidence_service import validate_analysis
from .test_core import data, BLOCKS, req
from . import test_core as core

class ProviderTests(SimpleTestCase):
    @patch.dict('os.environ',{'GEMINI_API_KEY':'fake','GROQ_API_KEY':'fake'},clear=True)
    def test_malformed_primary_uses_validated_fallback(self):
        with patch('google.genai.Client') as gemini,patch('groq.Groq') as groq,patch.object(providers,'_primary_paused_until',0):
            gemini.return_value.__enter__.return_value.models.generate_content.return_value.text='{}'
            groq.return_value.__enter__.return_value.chat.completions.create.return_value.choices=[MagicMock(message=MagicMock(content=json.dumps(data())))]
            result,meta=providers.generate(ResumeOutput,'Analyze',{},lambda out:validate_analysis(out,BLOCKS,[req()],date.today()))
            self.assertEqual(meta['provider'],'groq');self.assertEqual(result['requirement_matches'][0]['evidence_level'],'strong')
            self.assertEqual(gemini.call_count,1);self.assertEqual(groq.call_count,1)
            self.assertEqual(groq.call_args.kwargs['max_retries'],0)
    @patch.dict('os.environ',{'GEMINI_API_KEY':'fake','GROQ_API_KEY':'fake'},clear=True)
    def test_bad_evidence_primary_uses_fallback(self):
        bad=data();bad['requirement_matches'][0]['source_refs'][0]['exact_quote']='Fake quote'
        with patch('google.genai.Client') as gemini,patch('groq.Groq') as groq,patch.object(providers,'_primary_paused_until',0):
            gemini.return_value.__enter__.return_value.models.generate_content.return_value.text=json.dumps(bad)
            groq.return_value.__enter__.return_value.chat.completions.create.return_value.choices=[MagicMock(message=MagicMock(content=json.dumps(data())))]
            _,meta=providers.generate(ResumeOutput,'Analyze',{},lambda out:validate_analysis(out,BLOCKS,[req()],date.today()))
            self.assertEqual(meta['provider'],'groq')
    def test_invented_month_dates_rejected(self):
        d=data();d['candidate']['experience']=[{'id':'e1','role':'Developer','organization':None,'start_date':'2024-01','end_date':'2025-01','date_precision':'month','technologies':['Python'],'source_refs':[{'block_id':'p1-b2','exact_quote':'Built Python API with tests.'}]}]
        with self.assertRaises(ValueError):validate_analysis(ResumeOutput.model_validate(d),BLOCKS,[req()],date.today())
    def test_parent_technology_capped(self):
        d=data();d['candidate']['projects'][0]['technologies']=['Django']
        d['candidate']['projects'][0]['source_refs']=[{'block_id':'p1-b3','exact_quote':'Built Django API.'}]
        d['requirement_matches'][0]['source_refs']=[{'block_id':'p1-b3','exact_quote':'Built Django API.'}]
        out=validate_analysis(ResumeOutput.model_validate(d),BLOCKS+[{'id':'p1-b3','page':1,'text':'Built Django API.'}],[req()],date.today())
        self.assertEqual(out['requirement_matches'][0]['evidence_level'],'moderate')

class RevisionTests(TestCase):
    setUp=core.WorkflowTests.setUp
    tearDown=core.WorkflowTests.tearDown
    def setup_post(self,**changes):
        r=self.requirement
        fields={'title':self.job.title,'description':self.job.description,'requirements-TOTAL_FORMS':'1','requirements-INITIAL_FORMS':'1','requirements-MIN_NUM_FORMS':'0','requirements-MAX_NUM_FORMS':'15','requirements-0-id':str(r.pk),'requirements-0-job':str(self.job.pk),'requirements-0-label':r.label,'requirements-0-canonical_key':r.canonical_key,'requirements-0-category':r.category,'requirements-0-weight':str(r.weight),'requirements-0-essential':'on','requirements-0-minimum_months':'','requirements-0-minimum_count':'','requirements-0-jd_quote':''}
        fields.update(changes)
        return self.client.post(f'/jobs/{self.job.pk}/setup/',fields)
    def test_weight_edit_recalculates_without_stale(self):
        response=self.setup_post(**{'requirements-0-weight':'3'})
        self.assertEqual(response.status_code,302);self.job.refresh_from_db();self.app.refresh_from_db();self.assertEqual(self.job.requirements_revision,1);self.assertEqual(self.app.processing_status,'complete');self.assertEqual(self.app.breakdown['total_weight'],6)
    def test_meaning_edit_marks_stale(self):
        response=self.setup_post(**{'requirements-0-label':'Python API development'})
        self.assertEqual(response.status_code,302);self.job.refresh_from_db();self.app.refresh_from_db();self.assertEqual(self.job.requirements_revision,2);self.assertEqual(self.app.processing_status,'stale');self.assertIsNone(self.app.score)
    def test_github_cache_and_score_unchanged(self):
        from recruitment.services.github_service import fetch_github
        self.app.candidate['supplied_links']['github']='https://github.com/example';self.app.save()
        payloads=[{'html_url':'https://github.com/example','type':'User'},[{'name':'api','description':'Python Django','language':'Python','updated_at':'2026-01-01','fork':False}],{'Python':500},{'content':''},[{'name':'Dockerfile'},{'name':'manage.py'}]]
        responses=[]
        for payload in payloads:
            response=MagicMock();response.status_code=200;response.iter_content.return_value=[json.dumps(payload).encode()];response.__enter__.return_value=response;responses.append(response)
        with patch('requests.Session') as session:
            session.return_value.get.side_effect=responses
            result=fetch_github(self.app);self.assertEqual(result.fetch_status,'complete');self.assertEqual(session.return_value.get.call_count,5)
            fetch_github(self.app);self.assertEqual(session.return_value.get.call_count,5)
        self.app.refresh_from_db();self.assertEqual(self.app.score,100)
