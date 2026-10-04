import uuid
from django.db import models

def upload_path(instance, filename):
    return f'resumes/{uuid.uuid4().hex}.pdf'

class Job(models.Model):
    title = models.CharField(max_length=150)
    description = models.TextField()
    requirements_revision = models.PositiveIntegerField(default=1)
    extraction_meta = models.JSONField(default=dict)
    requirements_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class JobRequirement(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='requirements')
    label = models.CharField(max_length=150)
    canonical_key = models.CharField(max_length=150)
    category = models.CharField(max_length=30, default='skills')
    essential = models.BooleanField(default=False)
    weight = models.PositiveSmallIntegerField(default=3)
    minimum_months = models.PositiveIntegerField(null=True, blank=True)
    minimum_count = models.PositiveIntegerField(null=True, blank=True)
    jd_quote = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    class Meta:
        ordering = ['display_order', 'id']
        constraints = [models.UniqueConstraint(fields=['job','canonical_key'], name='unique_job_requirement')]

class Application(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')
    original_file = models.FileField(upload_to=upload_path)
    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64)
    raw_text = models.TextField(blank=True)
    source_blocks = models.JSONField(default=list)
    candidate = models.JSONField(default=dict)
    analysis = models.JSONField(default=dict)
    analysis_revision = models.PositiveIntegerField(default=0)
    analysis_date = models.DateField(null=True)
    score = models.FloatField(null=True)
    breakdown = models.JSONField(default=dict)
    processing_status = models.CharField(max_length=20, default='queued')
    decision_status = models.CharField(max_length=20, default='pending')
    decision_reason = models.TextField(blank=True)
    error = models.TextField(blank=True)
    provider = models.CharField(max_length=30, blank=True)
    model = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    input_fingerprint = models.CharField(max_length=64, blank=True)
    processing_started_at = models.DateTimeField(null=True)
    analyzed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    @property
    def name(self): return self.candidate.get('name') or self.filename
    class Meta:
        constraints = [models.UniqueConstraint(fields=['job', 'sha256'], name='unique_resume_per_job')]

class GitHubAnalysis(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='github_analysis')
    username = models.CharField(max_length=50, blank=True)
    fetch_status = models.CharField(max_length=20, default='pending')
    snapshot = models.JSONField(default=dict)
    evidence = models.JSONField(default=list)
    fetched_at = models.DateTimeField(null=True)
    retry_at = models.DateTimeField(null=True)
    error = models.TextField(blank=True)

class InterviewGuide(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='interview_guide')
    generated_questions = models.JSONField(default=list)
    edited_questions = models.JSONField(default=list)
    status = models.CharField(max_length=20, default='pending')
    context_fingerprint = models.CharField(max_length=64, blank=True)
    edit_revision = models.PositiveIntegerField(default=0)
    provenance = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    generation_token = models.UUIDField(null=True, editable=False)
    processing_started_at = models.DateTimeField(null=True)
    generated_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def questions(self):
        return self.edited_questions or self.generated_questions

class CandidateFeedback(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='feedback')
    generated = models.JSONField(default=dict)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    context_revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
