from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from recruitment.models import Application, CandidateFeedback, GitHubAnalysis, Interview, Job, JobRequirement


class LandingTests(TestCase):
    def setUp(self):
        self.job = Job.objects.create(title='Backend Developer Intern · Synthetic evidence demo', description='Python backend role')
        self.application = Application.objects.create(job=self.job, filename='synthetic.pdf', sha256='a' * 64, provider='demo-fixture')

    def test_landing_and_dashboard_have_separate_templates_and_routes(self):
        self.assertEqual(reverse('home'), '/')
        self.assertEqual(reverse('dashboard'), '/dashboard/')
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'recruitment/landing.html')
        self.assertContains(response, 'Your résumé says')
        self.assertContains(response, '/dashboard/')
        self.assertContains(response, 'vendor/motion/motion-12.23.24.js')
        self.assertNotContains(response, 'css/app.css')
        response = self.client.get(reverse('dashboard'))
        self.assertTemplateUsed(response, 'recruitment/home.html')
        self.assertContains(response, 'Your hiring overview.')
        self.assertContains(response, 'css/app.css')
        self.assertNotContains(response, 'css/landing.css')

    def test_demo_link_requires_real_fixture_application(self):
        response = self.client.get('/')
        self.assertContains(response, 'data-demo-link')
        self.assertContains(response, reverse('workspace', args=[self.job.pk]))
        self.application.provider = 'gemini'
        self.application.save()
        self.assertNotContains(self.client.get('/'), 'data-demo-link')

    def test_empty_installation_has_no_broken_demo_link(self):
        self.job.delete()
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-demo-link')
        self.assertContains(response, '/dashboard/')

    @patch('recruitment.views.configured', return_value=False)
    def test_dashboard_counts_and_synthetic_display_preserve_database(self, configured):
        normal = Job.objects.create(title='A real opening', description='Not a fixture')
        Application.objects.create(job=normal, filename='other.pdf', sha256='b' * 64, decision_status='shortlisted')
        Interview.objects.create(application=self.application)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(len(response.context['jobs']), 2)
        self.assertEqual(response.context['application_count'], 2)
        self.assertEqual(response.context['pending_count'], 1)
        self.assertEqual(response.context['interview_count'], 1)
        self.assertContains(response, 'Synthetic demo data')
        self.assertContains(response, '<h3>Backend Developer Intern</h3>', html=True)
        self.assertContains(response, 'data-dismiss-notice')
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, 'Backend Developer Intern · Synthetic evidence demo')
        self.assertFalse(normal.applications.filter(provider='demo-fixture').exists())

    @patch('recruitment.services.providers.generate', side_effect=AssertionError('Landing must not call AI'))
    @patch('recruitment.services.github_service.fetch_github', side_effect=AssertionError('Landing must not fetch GitHub'))
    def test_landing_is_read_only_and_never_calls_providers(self, github, generate):
        models = [Job, JobRequirement, Application, Interview, CandidateFeedback, GitHubAnalysis]
        before = [list(model.objects.order_by('pk').values()) for model in models]
        self.client.get('/')
        self.client.get('/')
        self.assertEqual(before, [list(model.objects.order_by('pk').values()) for model in models])
        generate.assert_not_called()
        github.assert_not_called()

    def test_internal_navigation_and_existing_routes(self):
        response = self.client.get(reverse('job_create'))
        self.assertContains(response, 'href="/dashboard/" class="button secondary">Cancel')
        response = self.client.get(reverse('workspace', args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/dashboard/"')
        self.assertContains(response, 'View public site')
        self.assertEqual(self.client.get(reverse('candidate', args=[self.application.pk])).status_code, 200)
        interview = Interview.objects.create(application=self.application)
        self.assertEqual(self.client.get(reverse('interview', args=[interview.access_token])).status_code, 200)
