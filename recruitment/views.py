import json
from datetime import timedelta
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse, FileResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Job, JobRequirement, Application, Interview, CandidateFeedback
from .forms import JobForm, RequirementSet
from .services import ai_service, resume_service, github_service, interview_service, feedback_service
from .services.providers import configured
from .services.scoring_service import VALUES

def landing(request):
    demo_job = Job.objects.filter(applications__provider='demo-fixture').distinct().order_by('-created_at').first()
    return render(request, 'recruitment/landing.html', {'demo_job': demo_job})

def home(request):
    jobs = list(Job.objects.order_by('-created_at').prefetch_related('applications', 'requirements'))
    for job in jobs:
        job.is_synthetic_demo = any(app.provider == 'demo-fixture' for app in job.applications.all())
        job.display_title = job.title
        if job.is_synthetic_demo:
            job.display_title = job.title.removesuffix(' · Synthetic evidence demo')
    return render(request, 'recruitment/home.html', {
        'jobs': jobs, 'ai_configured': configured(),
        'application_count': Application.objects.count(),
        'pending_count': Application.objects.filter(decision_status='pending').count(),
        'interview_count': Interview.objects.count(),
    })

def job_create(request):
    form=JobForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        job=form.save()
        try:
            data,meta=ai_service.extract_job_requirements(job.title,job.description)
            job.extraction_meta={**meta,'generated_at':timezone.now().isoformat()}; job.save(update_fields=['extraction_meta'])
            for n,r in enumerate(data['requirements']): JobRequirement.objects.create(job=job,display_order=n,**r)
            messages.success(request,'Suggested requirements extracted. Review and approve them before upload.')
        except Exception as exc: messages.warning(request,str(exc)+' Add requirements manually below.')
        return redirect('job_setup',pk=job.pk)
    return render(request,'recruitment/create.html',{'form':form})

def semantic_requirements(job):
    return list(job.requirements.order_by('id').values('id','label','canonical_key','category','minimum_months','minimum_count'))

def job_setup(request,pk):
    job=get_object_or_404(Job,pk=pk)
    form=JobForm(request.POST or None,instance=job)
    formset=RequirementSet(request.POST or None,instance=job,prefix='requirements')
    if request.method=='POST':
        before=semantic_requirements(job); old=Job.objects.get(pk=pk); description_changed=request.POST.get('description','')!=old.description
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save(); formset.save()
                for n,r in enumerate(job.requirements.all()): r.display_order=n; r.save(update_fields=['display_order'])
                changed=before!=semantic_requirements(job) or description_changed
                if changed:
                    job.requirements_revision+=1; job.question_set={}
                    job.applications.update(processing_status='stale',score=None)
                if job.title!=old.title: job.question_set={}
                job.requirements_approved=True; job.save()
                if not changed:
                    for app in job.applications.filter(processing_status='complete'): resume_service.rescore(app)
            messages.success(request,'Requirements approved. Scores use your priorities.')
            return redirect('workspace',pk=job.pk)
    return render(request,'recruitment/setup.html',{'job':job,'form':form,'formset':formset})

def workspace(request,pk):
    job=get_object_or_404(Job,pk=pk)
    apps=list(job.applications.all()); ranked=[a for a in apps if a.processing_status=='complete' and a.analysis_revision==job.requirements_revision and a.score is not None]
    ranked.sort(key=lambda a:(-a.score,a.breakdown.get('essential_gaps',0),a.pk))
    if request.GET.get('sort')=='coverage': ranked.sort(key=lambda a:(-a.breakdown.get('coverage',0),-a.score,a.pk))
    def number(key):
        try: return max(0,float(request.GET.get(key) or 0))
        except (ValueError,TypeError): return 0
    query=request.GET.get('q','').lower(); status=request.GET.get('status',''); req=request.GET.get('requirement',''); level=request.GET.get('level','mentioned')
    filtered=[]
    for a in ranked:
        if query and query not in a.name.lower(): continue
        if status and a.decision_status!=status: continue
        if a.score<number('minimum'): continue
        if a.breakdown.get('project_count',0)<number('projects') or a.breakdown.get('experience_months',0)<number('months'): continue
        if req and not any(str(r['requirement_id'])==req and VALUES[r['evidence_level']]>=VALUES.get(level,.25) for r in a.breakdown['rows']): continue
        filtered.append(a)
    now=timezone.now(); pending=[]
    for a in apps:
        if a.processing_status in ['queued','failed','stale'] or (a.processing_status=='processing' and a.processing_started_at and now-a.processing_started_at>timedelta(seconds=90)):
            pending.append({'id':a.pk,'name':a.name,'url':reverse('process',args=[a.pk])})
    return render(request,'recruitment/workspace.html',{'job':job,'applications':filtered,'all_count':len(apps),'ranked_count':len(ranked),'pending_apps':[a for a in apps if a not in ranked],'processing_queue':pending,'requirements':job.requirements.all(),'ai_configured':configured(),'statuses':['pending','shortlisted','hold','rejected']})

@require_POST
def upload(request,pk):
    job=get_object_or_404(Job,pk=pk)
    if not job.requirements_approved: messages.error(request,'Approve requirements before uploading.'); return redirect('job_setup',pk=pk)
    files=request.FILES.getlist('resumes')
    if not files or len(files)>10: messages.error(request,'Select between one and ten PDFs.'); return redirect('workspace',pk=pk)
    for file in files:
        try: resume_service.upload_resume(job,file); messages.success(request,f'{file.name}: queued for analysis.')
        except Exception as exc: messages.error(request,f'{file.name}: {exc}')
    return redirect('workspace',pk=pk)

@require_POST
def process(request,pk):
    app=get_object_or_404(Application.objects.select_related('job'),pk=pk)
    if not app.job.requirements_approved: return JsonResponse({'error':'Approve requirements first.'},status=400)
    try:
        app=resume_service.process_application(app)
        return JsonResponse({'name':app.name,'score':app.score,'status':app.processing_status})
    except Exception as exc: return JsonResponse({'error':str(exc)},status=400)

def candidate_detail(request,pk):
    app=get_object_or_404(Application.objects.select_related('job'),pk=pk)
    interview=Interview.objects.filter(application=app).first()
    if interview: interview_service.finalize_expired(interview)
    rows=[]
    if app.analysis_revision==app.job.requirements_revision:
        sources={b['id']:b for b in app.source_blocks}
        for row in app.breakdown.get('rows',[]):
            row={**row,'refs':[{**r,'page':sources.get(r['block_id'],{}).get('page')} for r in row['source_refs']]}; rows.append(row)
    answers=[]
    if interview:
        evaluations={r['question_id']:r for r in interview.evaluation.get('responses',[])}
        answers=[{'question':q,'answer':interview.answers.get(q['id'],''),'evaluation':evaluations.get(q['id'])} for q in interview.questions]
    return render(request,'recruitment/detail.html',{'application':app,'job':app.job,'rows':rows,'interview':interview,'answers':answers,'github':getattr(app,'github_analysis',None),'statuses':['pending','shortlisted','hold','rejected'],'current':app.processing_status=='complete' and app.analysis_revision==app.job.requirements_revision})

def resume_file(request,pk):
    app=get_object_or_404(Application,pk=pk)
    return FileResponse(app.original_file.open('rb'),content_type='application/pdf',as_attachment=request.GET.get('download')=='1',filename=app.filename)

@require_POST
def decision(request,pk):
    app=get_object_or_404(Application,pk=pk)
    status=request.POST.get('status')
    if status not in ['pending','shortlisted','hold','rejected']: return HttpResponseBadRequest('Invalid decision')
    app.decision_status=status; app.decision_reason=request.POST.get('reason','')[:3000]; app.save(update_fields=['decision_status','decision_reason'])
    messages.success(request,'Recruiter decision saved. AI does not make hiring decisions.')
    return redirect('candidate',pk=pk)

@require_POST
def contact(request,pk):
    app=get_object_or_404(Application,pk=pk); email=request.POST.get('email','').strip()
    try:
        if email: validate_email(email)
        app.candidate={**app.candidate,'email':email or None,'phone':request.POST.get('phone','')[:100]}; app.save(update_fields=['candidate'])
        messages.success(request,'Contact information saved.')
    except ValidationError: messages.error(request,'Enter a valid email address.')
    return redirect('candidate',pk=pk)

@require_POST
def github(request,pk):
    app=get_object_or_404(Application.objects.select_related('job'),pk=pk)
    result=github_service.fetch_github(app,refresh=request.POST.get('refresh')=='1',confirm_owner=request.POST.get('confirm_owner')=='on')
    if result.error: messages.warning(request,result.error)
    else: messages.success(request,'Public GitHub evidence inspected. Resume score is unchanged.')
    return redirect('candidate',pk=pk)

@require_POST
def interview_create(request,pk):
    app=get_object_or_404(Application.objects.select_related('job'),pk=pk)
    interview_service.create_interview(app)
    return redirect('candidate',pk=pk)

def interview_page(request,token):
    interview=get_object_or_404(Interview.objects.select_related('application__job'),access_token=token)
    interview_service.finalize_expired(interview)
    state={'status':interview.status,'revision':interview.answer_revision,'answers':interview.answers,'server_now':timezone.now().isoformat(),'deadline':interview.deadline_at.isoformat() if interview.deadline_at else None,'url':reverse('interview_api',args=[token])}
    return render(request,'recruitment/interview.html',{'interview':interview,'state':state,'standalone':True})

@require_POST
def interview_api(request,token):
    interview=get_object_or_404(Interview,access_token=token)
    try:
        payload=json.loads(request.body)
        if not isinstance(payload,dict): raise ValueError('Invalid request')
        if payload.get('action')=='start': interview_service.start(interview)
        elif payload.get('action') in ['save','submit']:
            interview_service.save_answers(interview,payload.get('answers'),payload.get('revision'),payload['action']=='submit')
        else: raise ValueError('Invalid action')
        return JsonResponse({'status':interview.status,'revision':interview.answer_revision,'answers':interview.answers,'server_now':timezone.now().isoformat(),'deadline':interview.deadline_at.isoformat() if interview.deadline_at else None})
    except (ValueError,TypeError) as exc: return JsonResponse({'error':str(exc)},status=409)

@require_POST
def interview_evaluate(request,pk):
    app=get_object_or_404(Application,pk=pk); interview=get_object_or_404(Interview,application=app); interview_service.finalize_expired(interview)
    if interview.status!='submitted': messages.error(request,'Submit the interview before analysis.'); return redirect('candidate',pk=pk)
    if interview.evaluation: messages.info(request,'Saved evaluation is already available.'); return redirect('candidate',pk=pk)
    try:
        data,meta=ai_service.evaluate_interview(interview); data['source']=meta['provider']+' / '+meta['model']; data['provenance']={**meta,'generated_at':timezone.now().isoformat()}; interview.evaluation=data; interview.error=''; interview.save()
    except Exception as exc: interview.error=str(exc); interview.save(update_fields=['error']); messages.warning(request,str(exc))
    return redirect('candidate',pk=pk)

def feedback(request,pk):
    app=get_object_or_404(Application.objects.select_related('job'),pk=pk)
    if app.decision_status!='rejected': messages.error(request,'Feedback is available for recruiter-rejected applications.'); return redirect('candidate',pk=pk)
    draft,_=CandidateFeedback.objects.get_or_create(application=app)
    if request.method=='POST':
        if request.POST.get('action')=='generate':
            if draft.body and request.POST.get('replace')!='on': messages.error(request,'Confirm replacing your existing draft before regenerating.')
            else:
                try:
                    reason=request.POST.get('reason','').strip()
                    draft=feedback_service.generate_feedback(app,reason,request.POST.get('include_interview')=='on')
                    app.decision_reason=reason; app.save(update_fields=['decision_reason']); messages.success(request,'Draft prepared. Review and edit before opening Gmail.')
                except ValueError as exc: messages.error(request,str(exc))
        elif request.POST.get('action')=='save':
            email=request.POST.get('email','').strip()
            try:
                if email: validate_email(email)
                subject=request.POST.get('subject','').strip(); body=request.POST.get('body','')
                if not subject or len(subject)>200 or not body.strip() or len(body)>20000: raise ValueError('Enter a subject (up to 200 characters) and message (up to 20,000 characters).')
                draft.subject=subject; draft.body=body
                if not draft.generated: draft.context_revision=app.job.requirements_revision
                draft.save()
                app.candidate={**app.candidate,'email':email or None}; app.save(update_fields=['candidate']); messages.success(request,'Edited draft saved. Gmail opens this saved version.')
            except (ValueError,ValidationError) as exc: messages.error(request,str(exc))
        return redirect('feedback',pk=pk)
    compose={'email':app.candidate.get('email') or '', 'subject':draft.subject,'body':draft.body}
    return render(request,'recruitment/feedback.html',{'application':app,'job':app.job,'draft':draft,'compose':compose,'stale':draft.context_revision!=app.job.requirements_revision})
