"""Recruiter prompts grounded in supplied evidence; no answers or evaluations."""
import copy
import hashlib
import json
import re
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import Application, InterviewGuide
from ..schemas import GuideQuestion
from . import ai_service

PROMPT_VERSION = 'guide-v1'
LEASE_SECONDS = 90


class GuideError(ValueError):
    pass


class GuideConflict(GuideError):
    pass


def eligible(application):
    return (application.processing_status == 'complete'
            and application.analysis_revision == application.job.requirements_revision
            and application.job.requirements_approved
            and application.job.requirements.exists())


def context(application):
    requirements = ai_service.requirement_data(application.job)
    requirements.sort(key=lambda item: item['id'])
    ids = {item['id'] for item in requirements}
    blocks = {block['id']: block['text'] for block in application.source_blocks}
    private_links = [value for key, value in application.candidate.get('supplied_links', {}).items() if value]
    evidence = []
    for match in application.analysis.get('requirement_matches', []):
        if match['requirement_id'] not in ids:
            continue
        refs = []
        for ref in match.get('source_refs', []):
            quote = ref['exact_quote']
            if (quote and quote in blocks.get(ref['block_id'], '')
                    and not re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', quote)
                    and not any(link in quote for link in private_links)
                    and not any(value and value in quote for value in [application.candidate.get('phone')])):
                if ref not in refs:
                    refs.append(ref)
        evidence.append({'requirement_id': match['requirement_id'],
                         'evidence_level': match['evidence_level'], 'source_refs': refs})
    rows = application.breakdown.get('rows', [])
    gaps = [row for row in rows if row['requirement_id'] in ids and row.get('match', 0) < .75]
    candidates = gaps or [row for row in rows if row['requirement_id'] in ids]
    candidates.sort(key=lambda row: (not row.get('essential', False), row.get('match', 0), -row.get('effective_weight', 0), row['requirement_id']))
    clarification_id = candidates[0]['requirement_id'] if candidates else requirements[0]['id'] if requirements else None
    # No name, contact data, social URLs or unrelated raw résumé blocks go to AI.
    return {'job_title': application.job.title, 'job_description': application.job.description,
            'requirements': requirements, 'evidence': evidence,
            'clarification_requirement_id': clarification_id, 'clarification_has_gap': bool(gaps),
            'analysis_revision': application.analysis_revision, 'prompt_version': PROMPT_VERSION}


def fingerprint(application):
    return hashlib.sha256(json.dumps(context(application), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def stale(guide, application):
    return bool(guide.generated_questions) and (not eligible(application) or guide.context_fingerprint != fingerprint(application))


def ensure_pending(application):
    if application.decision_status == 'shortlisted':
        return InterviewGuide.objects.get_or_create(application=application)[0]
    return None


def situational_questions(application):
    # Shared server-owned scenarios: candidate-specific difficulty cannot drift.
    return [
        {'id': 'accountability', 'kind': 'situational',
         'question': 'You discover a mistake in your work that nobody else has noticed. It could affect a customer or colleague, and correcting it may delay delivery. What would you do first, who would you inform, and how would you follow through?',
         'purpose': 'Explore how the candidate explains taking responsibility, communicating impact, and following through. Discuss actions; do not infer underlying character.',
         'follow_up': 'What would you do if your first attempt to fix the problem did not work?',
         'requirement_ids': [], 'source_refs': []},
        {'id': 'priorities', 'kind': 'situational',
         'question': 'A deadline is approaching when a teammate asks for urgent help with another issue. How would you assess the request, balance your commitments, and communicate your plan?',
         'purpose': 'Explore prioritisation, communication, and responsibility when commitments compete. The same scenario is used for all candidates in this job.',
         'follow_up': 'What information would change your decision, and when would you ask for help?',
         'requirement_ids': [], 'source_refs': []},
    ]


def validate_personalised(output, payload):
    questions = output.model_dump()['questions']
    expected = {'profile-1': 'profile', 'profile-2': 'profile', 'profile-3': 'profile', 'clarification': 'clarification'}
    if {q['id']: q['kind'] for q in questions} != expected or len(questions) != 4:
        raise GuideError('The guide must contain three profile questions and one clarification.')
    evidence = {item['requirement_id']: item['source_refs'] for item in payload['evidence']}
    ids = {item['id'] for item in payload['requirements']}
    for question in questions:
        if not question['question'].strip() or not question['purpose'].strip():
            raise GuideError('Questions and purposes cannot be empty.')
        refs = question['source_refs']
        linked = question['requirement_ids']
        if not linked or len(set(linked)) != len(linked) or not set(linked) <= ids:
            raise GuideError('Question references an unknown requirement.')
        if question['kind'] == 'profile' and not refs:
            raise GuideError('Profile questions require actual supporting passages.')
        if question['kind'] == 'clarification' and linked != [payload['clarification_requirement_id']]:
            raise GuideError('Clarification must address the selected evidence gap.')
        allowed = [ref for id in linked for ref in evidence.get(id, [])]
        if any(ref not in allowed for ref in refs):
            raise GuideError('Question cites an unsupported or invented passage.')
        if len({(ref['block_id'], ref['exact_quote']) for ref in refs}) != len(refs):
            raise GuideError('Duplicate source references.')
        text = ' '.join(question[key] for key in ['question', 'purpose', 'follow_up'])
        # Named technologies/projects and quantified premises must come from
        # this question's actual cited evidence or linked requirements.
        supported_text = ' '.join([ref['exact_quote'] for ref in refs] + [item['label'] for item in payload['requirements'] if item['id'] in linked])
        if question['kind'] == 'profile':
            question_text = question['question'] + ' ' + question['follow_up']
            capitals = re.findall(r'\b[A-Z][A-Za-z0-9_-]*\b', question_text)
            generic = {'Could','Can','How','What','Which','Why','When','Where','Would','Did','Do','Describe','Explain','Tell','Walk','In','For','And','If','I','API','REST','HTTP','AI'}
            if any(word not in generic and word.lower() not in supported_text.lower() for word in capitals):
                raise GuideError('A named project or technology in the question is not supported by its citations.')
            if any(number not in supported_text for number in re.findall(r'\b\d+(?:\.\d+)?\b', question_text)):
                raise GuideError('A quantified premise is not supported by the cited passage.')
        if re.search(r'\b(liar|lying|fraud|dishonest|morality|religion|political beliefs)\b', text, re.I):
            raise GuideError('Questions must explore job-related actions without personal accusations.')
    return [next(q for q in questions if q['id'] == id) for id in expected]


def template_questions(payload):
    requirements = {item['id']: item for item in payload['requirements']}
    evidence = [item for item in payload['evidence'] if item['source_refs']]
    priority = {'strong': 0, 'moderate': 1, 'weak': 2, 'mentioned': 3, 'missing': 4}
    evidence.sort(key=lambda item: (priority[item['evidence_level']], item['requirement_id']))
    questions = []
    prompts = ['What decisions did you make, and why?', 'What was your own responsibility, and how did you check the result?', 'What challenge did you face, and what would you change next time?']
    followups = ['What alternatives did you consider?', 'Can you walk me through a concrete example?', 'How did you communicate that challenge or ask for help?']
    for index in range(3):
        item = evidence[index % len(evidence)] if evidence else None
        requirement = requirements[item['requirement_id']] if item else list(requirements.values())[index % len(requirements)]
        refs = copy.deepcopy(item['source_refs'][:1]) if item else []
        questions.append({'id': f'profile-{index+1}', 'kind': 'profile',
                          'question': (f'Could you expand on the quoted {requirement["label"]} passage? {prompts[index]}' if refs else f'Could you describe a relevant example involving {requirement["label"]}? {prompts[index]}'),
                          'purpose': ('Explore the supplied passage with a standard evidence-based prompt.' if refs else 'Standard prompt: limited supplied evidence; do not assume prior use.'),
                          'follow_up': followups[index], 'requirement_ids': [requirement['id']], 'source_refs': refs})
    requirement = requirements[payload['clarification_requirement_id']]
    questions.append({'id': 'clarification', 'kind': 'clarification',
                      'question': f'Could you share more detail about your experience with {requirement["label"]}, including any relevant work not described in the résumé?',
                      'purpose': 'Clarify a role requirement with limited supporting evidence. Missing detail is not proof of inability.' if payload['clarification_has_gap'] else 'Deepen the evidence for this role requirement; no specific shortcoming is established.',
                      'follow_up': 'What was your responsibility, and what evidence or example would help explain it?',
                      'requirement_ids': [requirement['id']],
                      'source_refs': copy.deepcopy(next((item['source_refs'][:1] for item in payload['evidence'] if item['requirement_id'] == requirement['id']), []))})
    return questions


def generate_guide(application, replace=False, revision=None):
    if application.decision_status != 'shortlisted':
        raise GuideError('Shortlist this candidate before preparing or regenerating a guide.')
    if not eligible(application):
        raise GuideError('Approve requirements and complete current résumé analysis before preparing a guide.')
    guide = ensure_pending(application)
    payload = context(application)
    before = fingerprint(application)
    if guide.generated_questions:
        if not replace:
            if stale(guide, application):
                raise GuideConflict('The saved guide is outdated. Explicitly regenerate it after review.')
            return guide
        if revision != guide.edit_revision:
            raise GuideConflict('The guide changed in another tab. Reload before regenerating.')
    token = uuid.uuid4()
    now = timezone.now()
    # Compare-and-set lease: no database transaction is held across provider calls.
    claimed = InterviewGuide.objects.filter(pk=guide.pk, edit_revision=guide.edit_revision).filter(
        ~Q(status='processing') | Q(processing_started_at__lt=now-timedelta(seconds=LEASE_SECONDS)) | Q(processing_started_at__isnull=True)
    ).update(status='processing', generation_token=token, processing_started_at=now, error='')
    if not claimed:
        raise GuideConflict('A guide is already being prepared. Wait, then reload; interrupted requests can be retried after 90 seconds.')
    try:
        try:
            if not any(item['source_refs'] for item in payload['evidence']):
                raise GuideError('There are no relevant cited passages for personalised AI questions.')
            questions, provenance = ai_service.generate_interview_guide(payload, lambda output: validate_personalised(output, payload))
            provenance = {**provenance, 'source': 'AI-generated guide', 'prompt_version': PROMPT_VERSION}
            error = ''
        except Exception:
            questions = template_questions(payload)
            provenance = {'source': 'Evidence-based template (AI unavailable or output could not be validated)', 'provider': 'template', 'model': 'evidence-prompts-v1', 'prompt_version': PROMPT_VERSION}
            error = 'Personalised AI questions were unavailable or could not be validated. These are labelled standard evidence-based prompts. Retry AI when available.'
        questions += situational_questions(application)
        # Recheck with fresh application/requirements; an old generation may not
        # overwrite a newer edit, another lease, or changed evidence.
        with transaction.atomic():
            current = Application.objects.select_related('job').get(pk=application.pk)
            if not eligible(current) or fingerprint(current) != before:
                raise GuideConflict('The evidence changed while preparing the guide. Review the current analysis and retry.')
            updated = InterviewGuide.objects.filter(pk=guide.pk, generation_token=token, edit_revision=guide.edit_revision).update(
                generated_questions=questions, edited_questions=[], status='ready', context_fingerprint=before,
                provenance={**provenance, 'generated_at':timezone.now().isoformat()}, error=error,
                edit_revision=guide.edit_revision+1, generated_at=timezone.now(), updated_at=timezone.now(), generation_token=None, processing_started_at=None)
            if not updated:
                raise GuideConflict('A newer edit or generation superseded this request. Reload the guide.')
    except Exception as exc:
        InterviewGuide.objects.filter(pk=guide.pk, generation_token=token).update(status='ready' if guide.generated_questions else 'failed', error=str(exc), generation_token=None, processing_started_at=None)
        raise
    guide.refresh_from_db()
    return guide


def save_edits(application, revision, edits):
    guide = InterviewGuide.objects.get(application=application)
    if not guide.generated_questions or stale(guide, application):
        raise GuideConflict('Regenerate the outdated guide before editing it.')
    if guide.status == 'processing':
        raise GuideConflict('Wait for generation to finish before editing.')
    if not isinstance(edits, list) or len(edits) != 6:
        raise GuideError('Save the complete six-question guide.')
    by_id = {q['id']: q for q in guide.generated_questions}
    if len({item.get('id') for item in edits if isinstance(item, dict)}) != 6:
        raise GuideError('Question IDs must be unique.')
    questions = []
    for item in edits:
        if not isinstance(item, dict) or set(item) != {'id', 'question', 'purpose', 'follow_up'} or item['id'] not in by_id:
            raise GuideError('Only question, purpose and follow-up text can be edited.')
        question = GuideQuestion.model_validate({**by_id[item['id']], **item}).model_dump()
        if not question['question'].strip() or not question['purpose'].strip():
            raise GuideError('Questions and purposes cannot be empty.')
        questions.append(question)
    questions = [next(q for q in questions if q['id'] == id) for id in by_id]
    saved = InterviewGuide.objects.filter(pk=guide.pk, edit_revision=revision).exclude(status='processing').update(edited_questions=questions, edit_revision=revision+1, updated_at=timezone.now())
    if not saved:
        raise GuideConflict('The guide was updated in another tab. Reload before saving.')
    guide.refresh_from_db()
    return guide
