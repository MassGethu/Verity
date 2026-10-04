import hashlib
import uuid
from django.core import signing
from django.db import IntegrityError, transaction
from ..models import Application
from ..storage import download_pdf, signed_url, MAX_PDF_BYTES
from .resume_service import extract_pdf


def prepare(job, files):
    if not job.requirements_approved:
        raise ValueError('Approve requirements before uploading.')
    if not isinstance(files, list) or not 1 <= len(files) <= 10:
        raise ValueError('Select between one and ten PDFs.')
    uploads = []
    for file in files:
        if not isinstance(file, dict) or not isinstance(file.get('name'), str) or not file['name'].lower().endswith('.pdf'):
            raise ValueError('Select PDF files only.')
        if type(file.get('size')) is not int or not 0 < file['size'] <= MAX_PDF_BYTES:
            raise ValueError('Each PDF must be at most 5 MB.')
    for file in files:
        key = f'resumes/{uuid.uuid4().hex}.pdf'
        ticket = signing.dumps({'job': job.pk, 'key': key, 'filename': file['name'][:255], 'size': file['size']}, salt='resume-upload')
        uploads.append({'url': signed_url(key, upload=True), 'ticket': ticket})
    return uploads


def complete(job, ticket):
    if not job.requirements_approved:
        raise ValueError('Approve requirements before uploading.')
    try:
        payload = signing.loads(ticket, salt='resume-upload', max_age=600)
    except (signing.BadSignature, TypeError):
        raise ValueError('Upload authorisation expired or is invalid. Please upload again.')
    if payload['job'] != job.pk:
        raise ValueError('Upload belongs to another job.')
    content = download_pdf(payload['key'])
    if len(content) != payload['size']:
        raise ValueError('Uploaded file size does not match. Please upload again.')
    raw, blocks = extract_pdf(content)
    digest = hashlib.sha256(content).hexdigest()
    if job.applications.filter(sha256=digest).exists():
        raise ValueError('Identical resume already uploaded for this job.')
    try:
        with transaction.atomic():
            return Application.objects.create(job=job, original_file=payload['key'], filename=payload['filename'],
                sha256=digest, raw_text=raw, source_blocks=blocks)
    except IntegrityError:
        raise ValueError('Identical resume already uploaded for this job.')
