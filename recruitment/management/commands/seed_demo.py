import hashlib, io, json
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from recruitment.models import Job, JobRequirement
from recruitment.services.demo_service import DEMO_JD, DEMO_REQUIREMENTS, fixture_analysis
from recruitment.services.ai_service import requirement_data
from recruitment.services.resume_service import upload_resume, process_application
from recruitment.services.scoring_service import calculate
from recruitment.services.github_service import username_from_url

class Command(BaseCommand):
    help='Create seven synthetic PDF resumes and an explicit offline fixture job. --live uses actual configured AI instead.'
    def add_arguments(self,parser):
        parser.add_argument('--live',action='store_true')
        parser.add_argument('--github-profile',default='')
    def handle(self,*args,**options):
        github=options['github_profile']
        if github:
            try: username_from_url(github)
            except Exception as exc: raise CommandError(str(exc))
        title='Backend Developer Intern · '+('Live demo' if options['live'] else 'Synthetic evidence demo')
        job,created=Job.objects.get_or_create(title=title,defaults={'description':DEMO_JD,'requirements_approved':True})
        if not created:
            self.stdout.write(f'Demo already exists at /jobs/{job.pk}/. Existing records were preserved.');return
        for n,(label,key,category,essential,weight,months,count) in enumerate(DEMO_REQUIREMENTS):
            JobRequirement.objects.create(job=job,label=label,canonical_key=key,category=category,essential=essential,weight=weight,minimum_months=months,minimum_count=count,display_order=n)
        fixtures=json.loads((settings.BASE_DIR/'demo/candidates.json').read_text())
        out=settings.BASE_DIR/'output/pdf'; out.mkdir(parents=True,exist_ok=True)
        styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name='ResumeLine',fontName='Helvetica',fontSize=10,leading=15,spaceAfter=11,textColor=colors.HexColor('#25454d')))
        for candidate in fixtures:
            lines=['Candidate: '+candidate['name'],'Email: '+candidate['email'],'Education: BSc Computer Science (synthetic)','Skills: '+', '.join(candidate['skills'])]
            if candidate.get('duration_claim'): lines.append('Claim: '+candidate['duration_claim'])
            for p in candidate['projects']:lines.append('Project: '+p['title']+' | '+p['text'])
            for e in candidate['experience']:lines.append('Experience: '+e['role']+' | '+e['organization']+' | '+e['start']+' | '+e['end']+' | '+e['text'])
            if candidate['name'].startswith('Farhan') and github:lines.append('GitHub: '+github)
            lines.append('Synthetic ALGOTHON demonstration resume. Not a real application.')
            path=out/(candidate['name'].split()[0].lower()+'.pdf')
            doc=SimpleDocTemplate(str(path),pagesize=(595,842),rightMargin=45,leftMargin=45,topMargin=45,bottomMargin=45)
            story=[Paragraph(escape(candidate['name']),styles['Title']),Paragraph('BACKEND DEVELOPER INTERN · SYNTHETIC PROFILE',styles['Heading3']),Spacer(1,20)]
            story.extend(Paragraph(escape(line),styles['ResumeLine']) for line in lines); doc.build(story)
            app=upload_resume(job,SimpleUploadedFile(path.name,path.read_bytes(),content_type='application/pdf'))
            if options['live']:
                try:process_application(app)
                except Exception as exc:self.stderr.write(f'{app.filename}: {exc}')
            else:
                today=timezone.localdate();data=fixture_analysis(app.source_blocks,requirement_data(job),today)
                app.candidate=data['candidate'];app.analysis=data;app.analysis_revision=job.requirements_revision;app.analysis_date=today;app.breakdown=calculate(requirement_data(job),data,today);app.score=app.breakdown['overall'];app.processing_status='complete';app.provider='demo-fixture';app.model='explicit-synthetic-rules-v1';app.prompt_version='v1';app.input_fingerprint=hashlib.sha256(app.raw_text.encode()).hexdigest();app.analyzed_at=timezone.now();app.save()
            self.stdout.write(f'{candidate["name"]}: {app.score if app.score is not None else "unranked"}')
        self.stdout.write(self.style.SUCCESS(f'Demo ready: http://127.0.0.1:8000/jobs/{job.pk}/'))
