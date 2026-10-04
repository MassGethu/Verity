import hashlib
from unittest.mock import patch
from django.core import signing
from django.test import TestCase, override_settings
from django.urls import reverse
from recruitment.models import Job, Application
from recruitment.services.cloud_upload_service import prepare, complete
from recruitment.storage import signed_url, download_pdf, StorageUnavailable
from .test_core import pdf_content

class DeploymentTests(TestCase):
    def setUp(self):
        self.job=Job.objects.create(title='Frontend',description='React',requirements_approved=True)

    @override_settings(VERITY_JUDGE_PASSWORD='test-workspace-password')
    def test_public_landing_protected_workspace_and_login(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/health/').status_code,200)
        self.assertRedirects(self.client.get('/dashboard/'),'/workspace-login/')
        self.assertEqual(self.client.post(reverse('upload_prepare',args=[self.job.pk]),data='{}',content_type='application/json').status_code,403)
        self.assertContains(self.client.post('/workspace-login/',{'password':'wrong'}),'Incorrect')
        self.assertRedirects(self.client.post('/workspace-login/',{'password':'test-workspace-password'}),'/dashboard/')
        self.assertEqual(self.client.get('/dashboard/')['Cache-Control'],'no-store')
        self.client.post('/workspace-logout/')
        self.assertEqual(self.client.get('/dashboard/').status_code,302)

    @override_settings(VERITY_JUDGE_PASSWORD='test-password')
    def test_password_rotation_revokes_access_and_csrf_is_required(self):
        self.client.post('/workspace-login/',{'password':'test-password'})
        with override_settings(VERITY_JUDGE_PASSWORD='rotated-password'):
            self.assertEqual(self.client.get('/dashboard/').status_code,302)
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post('/workspace-login/',{'password':'test-password'}).status_code,403)

    @patch('recruitment.services.cloud_upload_service.signed_url',return_value='https://example.supabase.co/signed')
    def test_prepare_only_approved_bounded_pdfs(self, url):
        for files in [[],[{'name':'a.pdf','size':6*1024*1024}],[{'name':'a.exe','size':12}],[{'name':'a.pdf','size':True}]]:
            with self.assertRaises(ValueError):prepare(self.job,files)
        result=prepare(self.job,[{'name':'candidate.pdf','size':123}])
        payload=signing.loads(result[0]['ticket'],salt='resume-upload')
        self.assertEqual(payload['job'],self.job.pk)
        self.assertTrue(payload['key'].startswith('resumes/'))
        self.job.requirements_approved=False
        with self.assertRaises(ValueError):prepare(self.job,[{'name':'a.pdf','size':123}])

    @patch('recruitment.services.cloud_upload_service.download_pdf')
    def test_completion_validates_content_and_prevents_replay(self, download):
        content=pdf_content();download.return_value=content
        ticket=signing.dumps({'job':self.job.pk,'key':'resumes/test.pdf','filename':'test.pdf','size':len(content)},salt='resume-upload')
        app=complete(self.job,ticket)
        self.assertEqual(app.sha256,hashlib.sha256(content).hexdigest())
        self.assertEqual(app.original_file.name,'resumes/test.pdf')
        self.assertIsNone(app.score)
        with self.assertRaises(ValueError):complete(self.job,ticket)
        self.assertEqual(Application.objects.count(),1)
        with self.assertRaises(ValueError):complete(self.job,ticket+'tampered')
        other=Job.objects.create(title='Other',requirements_approved=True)
        with self.assertRaises(ValueError):complete(other,ticket)

    @patch('recruitment.services.cloud_upload_service.download_pdf',return_value=b'not a PDF')
    def test_invalid_object_never_becomes_application(self, download):
        ticket=signing.dumps({'job':self.job.pk,'key':'resumes/test.pdf','filename':'test.pdf','size':9},salt='resume-upload')
        with self.assertRaises(ValueError):complete(self.job,ticket)
        self.assertFalse(Application.objects.exists())

    @override_settings(USE_SUPABASE=True)
    @patch('recruitment.services.cloud_upload_service.prepare',return_value=[{'ticket':'safe','url':'https://example.supabase.co/signed'}])
    def test_json_upload_endpoints_and_local_form_guard(self, mock):
        url=reverse('upload_prepare',args=[self.job.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        self.assertEqual(self.client.post(url,data='{bad',content_type='application/json').status_code,400)
        response=self.client.post(url,data='{"files":[{"name":"a.pdf","size":10}]}',content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('SERVICE_ROLE',response.content.decode())
        self.assertContains(self.client.get(reverse('workspace',args=[self.job.pk])),'cloud-upload-form')
        self.assertEqual(self.client.post(reverse('upload',args=[self.job.pk])).status_code,302)

    @override_settings(SUPABASE_URL='https://example.supabase.co',SUPABASE_STORAGE_BUCKET='resumes')
    @patch('recruitment.storage.storage_request')
    def test_signed_urls_use_private_origin_and_reject_foreign_origin(self, request):
        response=request.return_value.__enter__.return_value
        response.json.return_value={'url':'/object/upload/sign/resumes/resumes/a.pdf?token=signed'}
        self.assertTrue(signed_url('resumes/a.pdf',upload=True).startswith('https://example.supabase.co/storage/v1/'))
        response.json.return_value={'url':'https://evil.example/file'}
        with self.assertRaises(StorageUnavailable):signed_url('resumes/a.pdf')

    @override_settings(USE_SUPABASE=True)
    @patch('recruitment.storage.signed_url',return_value='https://example.supabase.co/file?token=signed')
    def test_resume_redirect_does_not_stream_large_pdf_through_vercel(self, mock):
        app=Application.objects.create(job=self.job,original_file='resumes/a.pdf',filename='candidate.pdf',sha256='a'*64)
        result=self.client.get(reverse('resume',args=[app.pk])+'?download=1')
        self.assertEqual(result.status_code,302)
        self.assertIn('download=candidate.pdf',result.url)
        self.assertEqual(result['Cache-Control'],'no-store')
