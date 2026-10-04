from django.utils import timezone
from ..models import CandidateFeedback
from . import ai_service

def generate_feedback(application,reason,include_interview=False):
    if application.decision_status!='rejected': raise ValueError('Feedback is available after a recruiter rejects the application.')
    if not reason.strip(): raise ValueError('Enter a job-related reason first.')
    if application.processing_status!='complete' or application.analysis_revision!=application.job.requirements_revision: raise ValueError('Complete current analysis before generating feedback.')
    try:
        data,meta=ai_service.generate_candidate_feedback(application,reason,include_interview)
        data['source']=meta['provider']+' / '+meta['model']; data['provenance']={**meta,'generated_at':timezone.now().isoformat()}
    except Exception:
        strong=[r['label'] for r in application.breakdown['rows'] if r['match']>=.75]
        gaps=[r['label'] for r in application.breakdown['rows'] if r['match']<.75]
        data={'strengths':['Supplied evidence supports: '+', '.join(strong)] if strong else ['Review the supplied resume for strengths.'], 'weaknesses':['More evidence is needed for: '+', '.join(gaps)] if gaps else [],'opportunities':['Add concrete project examples and outcomes for requirements with limited evidence.'],'role_challenges':[reason],'improvement_steps':['Describe your responsibilities, implementation details, and relevant project results.'],'subject':f'Feedback on your application for {application.job.title}', 'body':f'Thank you for applying for {application.job.title}.\n\nRecruiter feedback: {reason}\n\n'+('Your supplied evidence supports '+', '.join(strong)+'.\n\n' if strong else '')+('For similar roles, consider adding concrete project or work examples for '+', '.join(gaps)+'.\n\n' if gaps else '')+'Thank you for your time.','source':'Editable factual template (AI unavailable)'}
    feedback,_=CandidateFeedback.objects.get_or_create(application=application)
    feedback.generated=data; feedback.subject=data['subject'][:200]; feedback.body=data['body']; feedback.context_revision=application.job.requirements_revision; feedback.save()
    return feedback
