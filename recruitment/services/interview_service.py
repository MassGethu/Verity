from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from ..models import Interview, Job
from . import ai_service

DEFAULT_QUESTIONS=[
 {'id':'q1','scenario':'A deadline is approaching when a teammate asks for urgent help with a production issue. How would you decide what to do and communicate your plan?','dimensions':['Prioritisation','Communication','Risk awareness'],'rubric':'Consider business impact, clarify urgency, communicate tradeoffs, seek help or escalation when necessary.'},
 {'id':'q2','scenario':'You discover a mistake in your work that nobody else has noticed. Fixing it may delay delivery. What would you do?','dimensions':['Accountability','Communication','Problem solving'],'rubric':'Explain impact, communicate promptly, propose a correction and prevent recurrence. Evaluate reasoning, not personal morality.'},
 {'id':'q3','scenario':'Two teammates disagree about a technical approach. You need to move the project forward. How would you handle the disagreement?','dimensions':['Communication','Problem solving','Prioritisation'],'rubric':'Clarify goals and constraints, compare evidence, propose a proportionate experiment or decision process.'},
]
def create_interview(application):
    if hasattr(application,'interview'): return application.interview
    job=application.job
    if not job.question_set:
        try:
            data,meta=ai_service.generate_interview_questions(job); data['source']=meta['provider']+' / '+meta['model']; data['provenance']={**meta,'generated_at':timezone.now().isoformat()}
        except Exception:
            data={'questions':DEFAULT_QUESTIONS,'source':'Standard scenarios (AI generation unavailable)'}
        Job.objects.filter(pk=job.pk,question_set={}).update(question_set=data)
        job.refresh_from_db()
    return Interview.objects.get_or_create(application=application,defaults={'questions':job.question_set['questions'],'question_source':job.question_set['source']})[0]

def finalize_expired(interview):
    now=timezone.now()
    Interview.objects.filter(pk=interview.pk,status='active',deadline_at__lte=now).update(status='submitted',submitted_at=interview.deadline_at)
    interview.refresh_from_db(); return interview

def start(interview):
    now=timezone.now()
    Interview.objects.filter(pk=interview.pk,status='ready').update(status='active',started_at=now,deadline_at=now+timedelta(minutes=6))
    interview.refresh_from_db(); return interview

def save_answers(interview,answers,revision,submit=False):
    finalize_expired(interview)
    if interview.status=='submitted': return interview
    if interview.status!='active': raise ValueError('Start the interview first.')
    ids={q['id'] for q in interview.questions}
    if not isinstance(answers,dict) or set(answers)!=ids or any(not isinstance(v,str) or len(v)>12000 for v in answers.values()): raise ValueError('Invalid answer snapshot.')
    if not isinstance(revision,int) or isinstance(revision,bool): raise ValueError('Invalid answer revision.')
    now=timezone.now()
    with transaction.atomic():
        values={'answers':answers,'answer_revision':revision+1}
        if submit: values.update(status='submitted',submitted_at=now)
        updated=Interview.objects.filter(pk=interview.pk,status='active',answer_revision=revision,deadline_at__gt=now).update(**values)
        if not updated:
            finalize_expired(interview)
            if interview.status=='submitted': return interview
            raise ValueError('Answer revision conflict. Reload to recover the latest saved answers.')
    interview.refresh_from_db(); return interview
