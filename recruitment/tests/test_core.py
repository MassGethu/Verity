import copy, io, json, tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from reportlab.pdfgen import canvas
from recruitment.models import Job, JobRequirement, Application, Interview, CandidateFeedback
from recruitment.schemas import ResumeOutput
from recruitment.services.scoring_service import calculate, relevant_months, canonical
from recruitment.services.evidence_service import validate_analysis
from recruitment.services.resume_service import extract_pdf, upload_resume, process_application
from recruitment.services.interview_service import DEFAULT_QUESTIONS, start, save_answers, finalize_expired
from recruitment.services.feedback_service import generate_feedback
from recruitment.services.github_service import username_from_url, fetch_github, GitHubError
from recruitment.services.providers import generate, AIUnavailable
from recruitment.services.demo_service import fixture_analysis
from recruitment.services.ai_service import requirement_data

def pdf_content(text='Candidate: Test Candidate\nEmail: test@example.com\nEducation: BSc Computer Science (synthetic)\nSkills: Python, Django\nProject: API | Built a Python and Django API with SQL validation and Git reviews.'):
    buffer=io.BytesIO();c=canvas.Canvas(buffer);y=800
    for line in text.splitlines():c.drawString(40,y,line);y-=20
    c.save();return buffer.getvalue()
def req(id=1,key='python',category='skills',weight=5,essential=True,months=None,count=None):
    return {'id':id,'label':key.title(),'canonical_key':key,'category':category,'weight':weight,'essential':essential,'minimum_months':months,'minimum_count':count}
def data(level='strong'):
    return {'candidate':{'name':'Test','email':'test@example.com','phone':None,'education':[],'skills':['Python'],'experience':[],'projects':[{'id':'p1','title':'API','description':'Built API','technologies':['Python'],'source_refs':[{'block_id':'p1-b2','exact_quote':'Built Python API with tests.'}]}],'achievements':[],'certifications':[],'supplied_links':{k:None for k in ['github','linkedin','instagram','reddit','portfolio']}},'requirement_matches':[{'requirement_id':1,'relevance':'direct','evidence_level':level,'source_refs':[{'block_id':'p1-b2','exact_quote':'Built Python API with tests.'}],'relevant_project_ids':['p1'],'relevant_experience_ids':[],'explanation':'Project evidence'}],'claims':[],'review_flags':[]}
BLOCKS=[{'id':'p1-b1','page':1,'text':'Skills: Python, Django'},{'id':'p1-b2','page':1,'text':'Built Python API with tests.'}]

class ScoringTests(SimpleTestCase):
    def test_formula(self):
        d=data();d['requirement_matches']+= [{**d['requirement_matches'][0],'requirement_id':2,'evidence_level':'moderate'},{**d['requirement_matches'][0],'requirement_id':3,'evidence_level':'mentioned'}]
        result=calculate([req(),req(2,'django'),req(3,'docker',weight=2,essential=False)],d)
        self.assertAlmostEqual(result['overall'],100*18/22)
    def test_project_threshold_and_no_double_count(self):
        d=data();d['requirement_matches'][0]['relevant_project_ids']=['p1','p1']
        result=calculate([req(category='projects',count=2)],d)
        self.assertEqual(result['overall'],50);self.assertEqual(result['project_count'],1);self.assertEqual(result['essential_gaps'],1)
    def test_related_cap(self):
        d=data();d['requirement_matches'][0]['relevance']='related'
        self.assertEqual(calculate([req()],d)['overall'],40)
    def test_month_union(self):
        exps=[{'start_date':'2024-01','end_date':'2025-01','date_precision':'month'},{'start_date':'2024-06','end_date':'2025-06','date_precision':'month'},{'start_date':'2020','end_date':'2026','date_precision':'year'}]
        self.assertEqual(relevant_months(exps,date(2026,10,4)),17)
    def test_present_and_future_cap(self):
        self.assertEqual(relevant_months([{'start_date':'2025-01','end_date':'present','date_precision':'month'}],date(2026,1,1)),12)
    def test_alias_boundaries(self):
        self.assertEqual(canonical('Postgres'),'postgresql');self.assertEqual(canonical('JS'),'javascript');self.assertNotEqual(canonical('Java'),canonical('JavaScript'))
    def test_skills_only_cap(self):
        d=data();d['requirement_matches'][0].update(source_refs=[{'block_id':'p1-b1','exact_quote':'Skills: Python, Django'}],relevant_project_ids=[])
        out=validate_analysis(ResumeOutput.model_validate(d),BLOCKS,[req()],date.today())
        self.assertEqual(out['requirement_matches'][0]['evidence_level'],'mentioned')
    def test_fabricated_quote_rejected(self):
        d=data();d['requirement_matches'][0]['source_refs'][0]['exact_quote']='I am amazing at Python'
        with self.assertRaises(ValueError):validate_analysis(ResumeOutput.model_validate(d),BLOCKS,[req()],date.today())
    def test_missing_requirement_rejected(self):
        with self.assertRaises(ValueError):validate_analysis(ResumeOutput.model_validate(data()),BLOCKS,[req(),req(2,'django')],date.today())
    def test_duplicate_requirements_rejected(self):
        d=data();d['requirement_matches']*=2
        with self.assertRaises(ValueError):validate_analysis(ResumeOutput.model_validate(d),BLOCKS,[req()],date.today())
    def test_pdf_extraction_and_invalid(self):
        raw,blocks=extract_pdf(pdf_content());self.assertIn('Test Candidate',raw);self.assertTrue(blocks[0]['id'].startswith('p1-b'))
        with self.assertRaises(ValueError):extract_pdf(b'not a pdf')
        with self.assertRaises(ValueError):extract_pdf(pdf_content(''))
    @patch.dict('os.environ',{},clear=True)
    def test_provider_missing(self):
        with self.assertRaises(AIUnavailable):generate(ResumeOutput,'task',{})

class WorkflowTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.override=override_settings(MEDIA_ROOT=self.tmp.name);self.override.enable()
        self.job=Job.objects.create(title='Backend Intern',description='Python and Django backend role',requirements_approved=True)
        self.requirement=JobRequirement.objects.create(job=self.job,label='Python',canonical_key='python',weight=5,essential=True)
        self.app=upload_resume(self.job,SimpleUploadedFile('test.pdf',pdf_content()))
        d=data();d['requirement_matches'][0]['requirement_id']=self.requirement.pk
        self.app.analysis=d;self.app.candidate=d['candidate'];self.app.analysis_revision=1;self.app.analysis_date=date.today();self.app.processing_status='complete';self.app.breakdown=calculate(requirement_data(self.job),d);self.app.score=100;self.app.save()
    def tearDown(self):self.override.disable();self.tmp.cleanup()
    def test_duplicate_upload(self):
        with self.assertRaises(ValueError):upload_resume(self.job,SimpleUploadedFile('other.pdf',self.app.original_file.read()))
    def test_all_pages_render(self):
        for url in ['/',reverse('job_create'),reverse('workspace',args=[self.job.pk]),reverse('job_setup',args=[self.job.pk]),reverse('candidate',args=[self.app.pk])]:self.assertEqual(self.client.get(url).status_code,200,url)
    def test_filters_and_order(self):
        response=self.client.get(reverse('workspace',args=[self.job.pk]),{'q':'Test','minimum':'90','requirement':str(self.requirement.pk),'level':'strong'})
        self.assertEqual(len(response.context['applications']),1)
        self.assertEqual(len(self.client.get(reverse('workspace',args=[self.job.pk]),{'q':'Nobody'}).context['applications']),0)
        self.app.processing_status='stale';self.app.save()
        self.assertEqual(len(self.client.get(reverse('workspace',args=[self.job.pk])).context['applications']),0)
    def test_processing_failure_null_score(self):
        self.app.processing_status='queued';self.app.save()
        with patch('recruitment.services.resume_service.analyze_resume',side_effect=AIUnavailable('Quota')):
            with self.assertRaises(AIUnavailable):process_application(self.app)
        self.app.refresh_from_db();self.assertIsNone(self.app.score);self.assertEqual(self.app.processing_status,'failed')
    def test_processing_completed_not_replaced(self):
        with patch('recruitment.services.resume_service.analyze_resume') as mock:process_application(self.app);mock.assert_not_called()
    def test_missing_github_neutral(self):
        before=self.app.score;result=fetch_github(self.app);self.app.refresh_from_db();self.assertEqual(self.app.score,before);self.assertEqual(result.fetch_status,'failed')
    def test_github_url_validation(self):
        self.assertEqual(username_from_url('https://github.com/example'),'example')
        for url in ['https://evil.com/example','http://github.com/example','https://github.com/example/repo','https://github.com/settings']:
            with self.assertRaises(GitHubError):username_from_url(url)
        self.assertEqual(username_from_url('https://github.com/example/repo',True),'example')
    def test_interview_deadline_refresh_and_conflict(self):
        interview=Interview.objects.create(application=self.app,questions=DEFAULT_QUESTIONS)
        start(interview);deadline=interview.deadline_at;start(interview);self.assertEqual(interview.deadline_at,deadline)
        answers={q['id']:'My reasoning' for q in DEFAULT_QUESTIONS};save_answers(interview,answers,0)
        self.assertEqual(interview.answer_revision,1)
        with self.assertRaises(ValueError):save_answers(interview,{**answers,'q1':'Old snapshot'},0)
        self.assertEqual(self.client.get(reverse('interview',args=[interview.access_token])).status_code,200)
        Interview.objects.filter(pk=interview.pk).update(deadline_at=timezone.now()-timedelta(seconds=1));interview.refresh_from_db()
        save_answers(interview,{**answers,'q1':'Late edit'},1)
        self.assertEqual(interview.status,'submitted');self.assertEqual(interview.answers['q1'],'My reasoning')
    def test_interview_duplicate_submission(self):
        i=Interview.objects.create(application=self.app,questions=DEFAULT_QUESTIONS);start(i);answers={q['id']:'Answer' for q in DEFAULT_QUESTIONS};save_answers(i,answers,0,True);save_answers(i,answers,0,True);self.assertEqual(i.answer_revision,1)
    def test_interview_evaluation_failure_preserves_answers(self):
        i=Interview.objects.create(application=self.app,questions=DEFAULT_QUESTIONS,status='submitted',answers={'q1':'Original'})
        with patch('recruitment.services.ai_service.evaluate_interview',side_effect=AIUnavailable('Unavailable')):self.client.post(reverse('interview_evaluate',args=[self.app.pk]))
        i.refresh_from_db();self.assertEqual(i.answers['q1'],'Original');self.assertTrue(i.error)
    def test_feedback_requires_rejection(self):
        with self.assertRaises(ValueError):generate_feedback(self.app,'Missing deployment evidence')
    def test_feedback_fallback_and_edit_persistence(self):
        self.app.decision_status='rejected';self.app.save()
        with patch('recruitment.services.ai_service.generate_candidate_feedback',side_effect=AIUnavailable('Unavailable')):draft=generate_feedback(self.app,'More deployment evidence needed')
        self.assertIn('template',draft.generated['source'])
        response=self.client.post(reverse('feedback',args=[self.app.pk]),{'action':'save','email':'edited@example.com','subject':'Your application','body':'Edited feedback with Unicode ✓\nNew line'})
        self.assertEqual(response.status_code,302);draft.refresh_from_db();self.assertIn('Edited feedback',draft.body)
        response=self.client.get(reverse('feedback',args=[self.app.pk]));self.assertEqual(response.context['compose']['email'],'edited@example.com');self.assertIn('✓',response.context['compose']['body'])
    def test_decision_is_manual(self):
        self.client.post(reverse('decision',args=[self.app.pk]),{'status':'shortlisted','reason':'Evidence reviewed'})
        self.app.refresh_from_db();self.assertEqual(self.app.decision_status,'shortlisted')
    def test_bad_json_interview_request(self):
        i=Interview.objects.create(application=self.app,questions=DEFAULT_QUESTIONS)
        response=self.client.post(reverse('interview_api',args=[i.access_token]),data='[]',content_type='application/json');self.assertEqual(response.status_code,409)
    def test_resume_download(self):
        response=self.client.get(reverse('resume',args=[self.app.pk]));self.assertEqual(response.status_code,200);self.assertEqual(response['Content-Type'],'application/pdf');response.close()

class DemoAndBoundaryTests(SimpleTestCase):
    def test_fixture_order_and_duration_flag(self):
        from django.conf import settings
        from recruitment.services.demo_service import DEMO_REQUIREMENTS
        requirements=[req(i+1,key,category,weight,essential,months,count) for i,(_,key,category,essential,weight,months,count) in enumerate(DEMO_REQUIREMENTS)]
        results={};analyses={}
        for name in ['asha','bharat','charu','deepak','esha','farhan','gita']:
            _,blocks=extract_pdf((settings.BASE_DIR/'output/pdf'/f'{name}.pdf').read_bytes())
            analysis=fixture_analysis(blocks,requirements,date(2026,10,4));analyses[name]=analysis;results[name]=calculate(requirements,analysis,date(2026,10,4))
        self.assertGreater(results['charu']['overall'],results['bharat']['overall'])
        self.assertEqual(results['asha']['overall'],results['gita']['overall'])
        self.assertEqual(results['asha']['project_count'],2)
        self.assertTrue(any(f['type']=='duration_evidence_gap' for f in analyses['esha']['review_flags']))
        self.assertTrue(any(r['label']=='Django' and r['gap'] for r in results['deepak']['rows']))
    def test_pdf_limits_and_encryption(self):
        from reportlab.lib.pdfencrypt import StandardEncryption
        buffer=io.BytesIO();c=canvas.Canvas(buffer)
        for _ in range(21):c.drawString(40,800,'Text');c.showPage()
        c.save()
        with self.assertRaisesRegex(ValueError,'20 pages'):extract_pdf(buffer.getvalue())
        with self.assertRaisesRegex(ValueError,'5 MB'):extract_pdf(b'%PDF-'+b'x'*(5*1024*1024))
        buffer=io.BytesIO();c=canvas.Canvas(buffer,encrypt=StandardEncryption('secret'));c.drawString(40,800,'Encrypted text');c.save()
        with self.assertRaises(ValueError):extract_pdf(buffer.getvalue())
    def test_unrelated_project_cannot_back_skill(self):
        d=data();r=req(key='aws');d['candidate']['skills'].append('AWS')
        d['requirement_matches'][0]['source_refs'].append({'block_id':'p1-b3','exact_quote':'Skills: AWS'})
        out=validate_analysis(ResumeOutput.model_validate(d),BLOCKS+[{'id':'p1-b3','page':1,'text':'Skills: AWS'}],[r],date.today())
        self.assertEqual(out['requirement_matches'][0]['evidence_level'],'mentioned')
    def test_unknown_timeline_no_duration_flag(self):
        d=data();d['candidate']['experience']=[{'id':'e1','role':'Developer','organization':None,'start_date':'2024','end_date':'2025','date_precision':'year','technologies':['Python'],'source_refs':[{'block_id':'p1-b2','exact_quote':'Built Python API with tests.'}]}]
        d['claims']=[{'id':'years','text':'3 years Python experience','canonical_key':'python','source_refs':[{'block_id':'p1-b3','exact_quote':'3 years Python experience'}],'supporting_refs':[],'support_level':'mentioned','claimed_months':36,'relevant_experience_ids':['e1'],'review_notes':[]}]
        out=validate_analysis(ResumeOutput.model_validate(d),BLOCKS+[{'id':'p1-b3','page':1,'text':'3 years Python experience'}],[req()],date.today())
        self.assertEqual(out['review_flags'],[])
