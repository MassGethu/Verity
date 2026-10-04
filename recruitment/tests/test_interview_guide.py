import copy
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from recruitment.models import Job, JobRequirement, Application, InterviewGuide
from recruitment.schemas import GuideOutput
from recruitment.services import interview_guide_service as service
from recruitment.services.providers import AIUnavailable


class GuideTests(TestCase):
    def setUp(self):
        self.job = Job.objects.create(title='Backend developer', description='Python, Django and Docker work.', requirements_approved=True)
        self.python = JobRequirement.objects.create(job=self.job,label='Python',canonical_key='python',essential=True,weight=5)
        self.django = JobRequirement.objects.create(job=self.job,label='Django',canonical_key='django',essential=True,weight=5)
        self.docker = JobRequirement.objects.create(job=self.job,label='Docker',canonical_key='docker',weight=2)
        self.refs = [{'block_id':'p1-b1','exact_quote':'Built a Python API with validation and tests.'},{'block_id':'p1-b2','exact_quote':'Implemented Django permissions for the booking project.'}]
        self.app = Application.objects.create(job=self.job,filename='synthetic.pdf',sha256='a'*64,processing_status='complete',analysis_revision=1,score=81.8,
            candidate={'name':'Synthetic Candidate','email':'private@example.com','phone':'9876543210','supplied_links':{'instagram':'https://instagram.com/private_person'}},
            source_blocks=[{'id':r['block_id'],'page':1,'text':r['exact_quote']} for r in self.refs]+[{'id':'p1-b3','page':1,'text':'private@example.com 9876543210 https://instagram.com/private_person'}],
            analysis={'requirement_matches':[{'requirement_id':self.python.pk,'evidence_level':'strong','source_refs':[self.refs[0]]},{'requirement_id':self.django.pk,'evidence_level':'moderate','source_refs':[self.refs[1]]},{'requirement_id':self.docker.pk,'evidence_level':'missing','source_refs':[]}]},
            breakdown={'rows':[{'requirement_id':self.python.pk,'match':1,'essential':True,'effective_weight':10,'source_refs':[self.refs[0]],'label':'Python','evidence_level':'strong','gap':False},{'requirement_id':self.django.pk,'match':.75,'essential':True,'effective_weight':10,'source_refs':[self.refs[1]],'label':'Django','evidence_level':'moderate','gap':False},{'requirement_id':self.docker.pk,'match':0,'essential':False,'effective_weight':2,'source_refs':[],'label':'Docker','evidence_level':'missing','gap':False}]})

    def output(self):
        return {'questions':[
            {'id':'profile-1','kind':'profile','question':'How did you test the Python API?','purpose':'Explore implementation choices.','follow_up':'What alternatives did you consider?','requirement_ids':[self.python.pk],'source_refs':[self.refs[0]]},
            {'id':'profile-2','kind':'profile','question':'How did you implement Django permissions?','purpose':'Explore access controls.','follow_up':'How did you test them?','requirement_ids':[self.django.pk],'source_refs':[self.refs[1]]},
            {'id':'profile-3','kind':'profile','question':'What was your own responsibility in the Python work?','purpose':'Clarify contribution.','follow_up':'What would you change?','requirement_ids':[self.python.pk],'source_refs':[self.refs[0]]},
            {'id':'clarification','kind':'clarification','question':'Could you describe any Docker work not mentioned in the résumé?','purpose':'Clarify limited evidence without assuming inability.','follow_up':'What was your responsibility?','requirement_ids':[self.docker.pk],'source_refs':[]},
        ]}

    def ai(self, payload, validator):
        return validator(GuideOutput.model_validate(self.output())), {'provider':'gemini','model':'mock-model','prompt_version':'v1','input_fingerprint':'abc'}

    def shortlist(self):
        return self.client.post(reverse('decision',args=[self.app.pk]),{'status':'shortlisted','reason':'Review relevant project evidence.'})

    def prepared(self):
        self.shortlist();self.app.refresh_from_db()
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=self.ai):
            return service.generate_guide(self.app)

    def test_shortlist_is_immediate_and_detail_auto_prepares_read_only(self):
        with patch('recruitment.services.ai_service.generate_interview_guide') as ai:
            self.assertEqual(self.shortlist().status_code,302); ai.assert_not_called()
        self.app.refresh_from_db();self.assertEqual(self.app.decision_status,'shortlisted');self.assertEqual(self.app.score,81.8)
        guide=self.app.interview_guide;self.assertEqual(guide.status,'pending')
        response=self.client.get(reverse('candidate',args=[self.app.pk]))
        self.assertTrue(response.context['guide_state']['auto_prepare']);self.assertContains(response,'Evidence-based Interview Guide')
        self.assertEqual(InterviewGuide.objects.count(),1)

    def test_generation_api_has_six_questions_provenance_and_no_score_impact(self):
        self.shortlist()
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=self.ai):
            response=self.client.post(reverse('guide_generate',args=[self.app.pk]),data=json.dumps({'revision':0,'replace':False}),content_type='application/json',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code,200)
        guide=InterviewGuide.objects.get(application=self.app)
        self.assertEqual([q['kind'] for q in guide.questions],['profile']*3+['clarification']+['situational']*2)
        self.assertEqual(guide.provenance['provider'],'gemini');self.assertEqual(guide.provenance['prompt_version'],'guide-v1')
        self.app.refresh_from_db();self.assertEqual(self.app.score,81.8);self.assertEqual(self.app.decision_status,'shortlisted')
        response=self.client.get(reverse('candidate',args=[self.app.pk]));self.assertFalse(response.context['guide_state']['auto_prepare'])
        self.assertContains(response,self.refs[0]['exact_quote']);self.assertContains(response,'page 1')

    def test_templates_are_truthfully_labelled_and_neutral_without_citations(self):
        self.shortlist();self.app.refresh_from_db()
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=AIUnavailable('No providers')):
            guide=service.generate_guide(self.app)
        self.assertEqual(guide.provenance['provider'],'template');self.assertIn('AI unavailable',guide.provenance['source']);self.assertTrue(guide.error)
        self.assertEqual(guide.questions[0]['source_refs'],[self.refs[0]])
        self.app.analysis={'requirement_matches':[]};self.app.save()
        with patch('recruitment.services.ai_service.generate_interview_guide') as ai:
            guide=service.generate_guide(self.app,replace=True,revision=guide.edit_revision);ai.assert_not_called()
        self.assertEqual(guide.questions[0]['source_refs'],[]);self.assertIn('limited supplied evidence',guide.questions[0]['purpose'])

    def test_invalid_ai_result_uses_template(self):
        self.shortlist();self.app.refresh_from_db()
        invalid=self.output();invalid['questions'][0]['source_refs'][0]={**self.refs[0],'exact_quote':'Invented achievement'}
        def invalid_ai(payload,validator):return validator(GuideOutput.model_validate(invalid)),{}
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=invalid_ai):guide=service.generate_guide(self.app)
        self.assertEqual(guide.provenance['provider'],'template');self.assertNotIn('Invented achievement',json.dumps(guide.questions))

    def test_contract_rejects_fabricated_sources_requirements_projects_and_accusations(self):
        payload=service.context(self.app)
        mutations=[lambda q:q.update(requirement_ids=[999]),lambda q:q.update(source_refs=[]),lambda q:q.update(question='How did you build ImaginaryCloud?'),lambda q:q.update(question='How did you achieve 90000 requests?'),lambda q:q.update(question='Why were you dishonest?'),lambda q:q.update(source_refs=[{'block_id':'fake','exact_quote':'Built a Python API with validation and tests.'}])]
        for mutate in mutations:
            output=self.output();mutate(output['questions'][0])
            with self.assertRaises(ValueError):service.validate_personalised(GuideOutput.model_validate(output),payload)
        output=self.output();output['questions'][3]['requirement_ids']=[self.python.pk]
        with self.assertRaises(ValueError):service.validate_personalised(GuideOutput.model_validate(output),payload)
        output=self.output();output['questions'][2]['id']='profile-1'
        with self.assertRaises(ValueError):service.validate_personalised(GuideOutput.model_validate(output),payload)

    def test_prompt_payload_excludes_contact_and_social_data(self):
        payload=json.dumps(service.context(self.app))
        for private in ['Synthetic Candidate','private@example.com','9876543210','instagram.com']:
            self.assertNotIn(private,payload)

    def test_scenarios_are_shared_and_do_not_claim_past_behaviour(self):
        one=service.situational_questions(self.app)
        self.app.candidate={'name':'Different person'}
        self.assertEqual(one,service.situational_questions(self.app))
        self.assertTrue(all(not q['source_refs'] and not q['requirement_ids'] for q in one))

    def test_current_analysis_and_shortlisting_are_prerequisites(self):
        with self.assertRaises(service.GuideError):service.generate_guide(self.app)
        self.shortlist();self.app.refresh_from_db();self.app.analysis_revision=0;self.app.save()
        with patch('recruitment.services.ai_service.generate_interview_guide') as ai:
            with self.assertRaises(service.GuideError):service.generate_guide(self.app)
            ai.assert_not_called()
        self.assertEqual(InterviewGuide.objects.get(application=self.app).status,'pending')

    def test_reuse_edits_revision_conflict_and_status_change(self):
        guide=self.prepared()
        edits=[{key:q[key] for key in ['id','question','purpose','follow_up']} for q in guide.questions]
        edits[0]['question']='Edited by the recruiter: what choices did you make?'
        guide=service.save_edits(self.app,guide.edit_revision,edits)
        with self.assertRaises(service.GuideConflict):service.save_edits(self.app,guide.edit_revision-1,edits)
        self.client.post(reverse('decision',args=[self.app.pk]),{'status':'hold'})
        self.assertEqual(InterviewGuide.objects.get(application=self.app).questions[0]['question'],edits[0]['question'])
        self.shortlist();self.app.refresh_from_db()
        with patch('recruitment.services.ai_service.generate_interview_guide') as ai:
            reused=service.generate_guide(self.app);ai.assert_not_called()
        self.assertEqual(reused.questions[0]['question'],edits[0]['question'])
        with self.assertRaises(service.GuideConflict):service.generate_guide(self.app,replace=True,revision=0)
        self.assertEqual(InterviewGuide.objects.get(application=self.app).questions[0]['question'],edits[0]['question'])
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=self.ai):new=service.generate_guide(self.app,replace=True,revision=guide.edit_revision)
        self.assertFalse(new.edited_questions);self.assertGreater(new.edit_revision,guide.edit_revision)

    def test_stale_requirements_and_rescore_preserve_guide_until_explicit_regeneration(self):
        guide=self.prepared()
        JobRequirement.objects.filter(pk=self.python.pk).update(weight=4)
        self.assertTrue(service.stale(guide,self.app))
        with self.assertRaises(service.GuideConflict):service.generate_guide(self.app)
        response=self.client.get(reverse('candidate',args=[self.app.pk]));self.assertTrue(response.context['guide_stale']);self.assertFalse(response.context['guide_state']['auto_prepare'])
        self.assertEqual(InterviewGuide.objects.get(application=self.app).generated_questions,guide.generated_questions)

    def test_concurrent_generation_and_interrupted_lease(self):
        self.shortlist();self.app.refresh_from_db();guide=self.app.interview_guide
        InterviewGuide.objects.filter(pk=guide.pk).update(status='processing',generation_token=uuid.uuid4(),processing_started_at=timezone.now())
        with self.assertRaises(service.GuideConflict):service.generate_guide(self.app)
        InterviewGuide.objects.filter(pk=guide.pk).update(processing_started_at=timezone.now()-timedelta(seconds=91))
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=self.ai):guide=service.generate_guide(self.app)
        self.assertEqual(guide.status,'ready');self.assertIsNone(guide.generation_token)

    def test_changed_evidence_during_provider_call_discards_result(self):
        self.shortlist();self.app.refresh_from_db()
        def changed(payload,validator):
            Job.objects.filter(pk=self.job.pk).update(title='Changed role')
            return self.ai(payload,validator)
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=changed):
            with self.assertRaises(service.GuideConflict):service.generate_guide(self.app)
        guide=InterviewGuide.objects.get(application=self.app);self.assertFalse(guide.generated_questions);self.assertEqual(guide.status,'failed')

    def test_newer_generation_cannot_be_overwritten(self):
        self.shortlist();self.app.refresh_from_db()
        def changed(payload,validator):
            InterviewGuide.objects.filter(application=self.app).update(generation_token=uuid.uuid4(),edit_revision=4,error='Newer generation')
            return self.ai(payload,validator)
        with patch('recruitment.services.ai_service.generate_interview_guide',side_effect=changed):
            with self.assertRaises(service.GuideConflict):service.generate_guide(self.app)
        guide=InterviewGuide.objects.get(application=self.app);self.assertEqual(guide.error,'Newer generation');self.assertEqual(guide.edit_revision,4)

    def test_invalid_requests_csrf_and_retired_routes(self):
        url=reverse('guide_generate',args=[self.app.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url).status_code,403)
        self.assertEqual(self.client.post(url,data='[]',content_type='application/json',HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,409)
        for url in [f'/applications/{self.app.pk}/interview/',f'/applications/{self.app.pk}/evaluate/','/interview/00000000-0000-0000-0000-000000000001/','/interview/00000000-0000-0000-0000-000000000001/api/']:
            self.assertEqual(self.client.get(url).status_code,404);self.assertEqual(self.client.post(url).status_code,404)

    def test_feedback_has_no_guide_or_interview_evaluation_input(self):
        from recruitment.services.ai_service import generate_candidate_feedback
        self.app.decision_status='rejected';self.app.save()
        with patch('recruitment.services.ai_service.generate',return_value=({},{})) as generate:
            generate_candidate_feedback(self.app,'Deployment evidence needed')
        payload=generate.call_args.args[2]
        self.assertNotIn('reviewed_interview',payload);self.assertNotIn('questions',payload)
        response=self.client.get(reverse('feedback',args=[self.app.pk]));self.assertNotContains(response,'include_interview')


class GuideMigrationTests(TransactionTestCase):
    def test_old_records_deleted_and_existing_shortlists_queued_without_losing_applications(self):
        executor=MigrationExecutor(connection)
        old_target=[('recruitment','0002_job_extraction_meta')]
        new_target=[('recruitment','0003_remove_job_question_set_interviewguide_and_more')]
        executor.migrate(old_target)
        old=executor.loader.project_state(old_target).apps
        JobOld=old.get_model('recruitment','Job');AppOld=old.get_model('recruitment','Application');InterviewOld=old.get_model('recruitment','Interview');FeedbackOld=old.get_model('recruitment','CandidateFeedback')
        job=JobOld.objects.create(title='Preserved job',description='Python',question_set={'questions':['old scenario']})
        app=AppOld.objects.create(job=job,filename='preserved.pdf',sha256='c'*64,decision_status='shortlisted',score=82)
        InterviewOld.objects.create(application=app,answers={'q1':'Old answer'},evaluation={'summary':'Old evaluation'})
        FeedbackOld.objects.create(application=app,subject='Saved draft',body='Recruiter edits')
        try:
            executor=MigrationExecutor(connection);executor.migrate(new_target)
            new=executor.loader.project_state(new_target).apps
            self.assertNotIn('recruitment_interview',connection.introspection.table_names())
            preserved=new.get_model('recruitment','Application').objects.get(pk=app.pk)
            self.assertEqual(preserved.score,82);self.assertEqual(preserved.decision_status,'shortlisted')
            self.assertEqual(new.get_model('recruitment','InterviewGuide').objects.get(application_id=app.pk).status,'pending')
            self.assertEqual(new.get_model('recruitment','CandidateFeedback').objects.get(application_id=app.pk).body,'Recruiter edits')
            self.assertNotIn('question_set',[field.name for field in new.get_model('recruitment','Job')._meta.fields])
        finally:
            MigrationExecutor(connection).migrate(new_target)
