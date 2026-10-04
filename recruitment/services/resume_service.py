import hashlib, io, re
from datetime import timedelta
import pdfplumber
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from ..models import Application, Job
from .ai_service import analyze_resume, requirement_data
from .scoring_service import calculate

def extract_pdf(content):
    if len(content)>5*1024*1024: raise ValueError('PDF exceeds 5 MB.')
    if not content.startswith(b'%PDF-'): raise ValueError('Please upload a valid PDF.')
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if len(pdf.pages)>20: raise ValueError('PDF exceeds 20 pages.')
            blocks=[]; pages=[]
            for page_number,page in enumerate(pdf.pages,1):
                text=page.extract_text() or ''; pages.append(text)
                # Lines preserve precise excerpts across common text PDF layouts.
                for n,line in enumerate(text.splitlines(),1):
                    line=re.sub(r'\s+',' ',line).strip()
                    if line: blocks.append({'id':f'p{page_number}-b{n}','page':page_number,'text':line})
    except ValueError: raise
    except Exception as exc: raise ValueError('This PDF could not be read. Encrypted or damaged PDFs are unsupported.') from exc
    raw='\n\n'.join(pages)
    if len(re.sub(r'\s','',raw))<100: raise ValueError('Little extractable text found. Please upload a text-based PDF; OCR is not supported.')
    if len(raw)>50000: raise ValueError('Resume exceeds 50,000 extracted characters. Please provide a shorter PDF.')
    return raw,blocks

def upload_resume(job,file):
    content=file.read(5*1024*1024+1); digest=hashlib.sha256(content).hexdigest()
    if job.applications.filter(sha256=digest).exists(): raise ValueError('Identical resume already uploaded for this job.')
    raw,blocks=extract_pdf(content)
    app=Application(job=job,filename=file.name[:255],sha256=digest,raw_text=raw,source_blocks=blocks)
    app.original_file.save('resume.pdf',ContentFile(content),save=False); app.save()
    return app

def process_application(app):
    now=timezone.now()
    if app.processing_status=='complete' and app.analysis_revision==app.job.requirements_revision: return app
    cutoff=now-timedelta(seconds=90)
    claimed=Application.objects.filter(pk=app.pk).exclude(processing_status='complete').exclude(processing_status='processing',processing_started_at__gte=cutoff).update(processing_status='processing',processing_started_at=now,error='',score=None)
    if not claimed: raise ValueError('This application is already processing. Retry after 90 seconds if interrupted.')
    revision=app.job.requirements_revision; reqs=requirement_data(app.job); today=timezone.localdate()
    try:
        if not reqs: raise ValueError('Approve at least one job requirement first.')
        data,meta=analyze_resume(app.source_blocks,reqs,today)
        breakdown=calculate(reqs,data,today)
        with transaction.atomic():
            latest_job=Job.objects.get(pk=app.job_id)
            if latest_job.requirements_revision!=revision: raise ValueError('Requirements changed during processing. Please retry.')
            breakdown=calculate(requirement_data(latest_job),data,today)
            Application.objects.filter(pk=app.pk).update(candidate=data['candidate'],analysis=data,analysis_revision=revision,analysis_date=today,breakdown=breakdown,score=breakdown['overall'],processing_status='complete',analyzed_at=timezone.now(),error='',**meta)
    except Exception as exc:
        Application.objects.filter(pk=app.pk).update(processing_status='failed',score=None,error=str(exc))
        raise
    app.refresh_from_db(); return app

def rescore(app):
    if app.analysis and app.analysis_revision==app.job.requirements_revision:
        app.breakdown=calculate(requirement_data(app.job),app.analysis,app.analysis_date)
        app.score=app.breakdown['overall']; app.save(update_fields=['breakdown','score'])
