from .providers import generate
from ..schemas import JobOutput, ResumeOutput, GuideOutput, FeedbackOutput
from .evidence_service import validate_analysis
from .scoring_service import canonical

def requirement_data(job):
    return list(job.requirements.values('id','label','canonical_key','category','essential','weight','minimum_months','minimum_count','jd_quote'))

def extract_job_requirements(title,description):
    def validate(out):
        data=out.model_dump(); seen=set()
        for r in data['requirements']:
            r['canonical_key']=canonical(r['canonical_key'])
            if not r['label'].strip() or not r['canonical_key'] or r['canonical_key'] in seen: raise ValueError('Duplicate or empty requirement')
            seen.add(r['canonical_key'])
            if not r['jd_quote'] or r['jd_quote'] not in description: raise ValueError('Requirement not grounded in JD')
            if r['minimum_months'] is not None and (r['category']!='experience' or r['minimum_months']<1): raise ValueError('Invalid duration requirement')
            if r['minimum_count'] is not None and (r['category']!='projects' or r['minimum_count']<1): raise ValueError('Invalid count requirement')
        return data
    return generate(JobOutput,'Extract 8–15 distinct job requirements when the JD supports that many; fewer is okay for a short JD. Only include job-related requirements explicitly in this JD. Categories: skills, projects, experience, education, expectations. Suggest importance 1–5; recruiter approves it. Include exact JD quotes. Do not include school prestige or personal/protected characteristics.',{'title':title,'description':description},validate)

def analyze_resume(blocks,requirements,today):
    task='''Extract candidate information, interpret every requirement, and map at most 15 job-relevant claims to supporting evidence. Each requirement ID appears exactly once. Every non-missing match requires exact source_refs from numbered blocks. Each exact_quote must be a verbatim substring of ONE block, preserving punctuation, spelling and spacing. Never join wrapped lines into one quote; cite each line using its own block_id. Use the same source reference objects in linked projects/experience and requirement matches where they support the same evidence. Cite date-bearing blocks for every experience date. Strong: explicit use with concrete implementation details/outcomes; moderate: explicit use without details; weak: vague or related use; mentioned: skills/summary assertion only; missing: absent. Repeated keywords do not add evidence. Projects/experience have unique IDs, exact citations, and technologies explicitly evidenced there. Link only relevant IDs. Related technologies are weak, except Django/Flask/FastAPI evidence may support Python at moderate and PostgreSQL/MySQL/SQLite may support SQL at moderate. Never conflate Java and JavaScript. Skills-list-only evidence is mentioned. Dates are YYYY-MM only when explicitly month-dated, YYYY for year-only; present for current end date. No inferred dates. Preserve nulls. Claim claimed_months is set only when an explicit numeric years/months assertion exists; cite it and link relevant dated experiences. review_flags only for two explicit conflicting statements about the same fact, with both exact quotes and cautious manual-review language. A shorter dated timeline is not proof of dishonesty; Python checks duration gaps. Do not infer names, emails, contact links. Non-GitHub supplied links are collected only, never evaluated.'''
    return generate(ResumeOutput,task,{'blocks':blocks,'requirements':requirements,'analysis_date':str(today)},lambda out:validate_analysis(out,blocks,requirements,today))

def generate_interview_guide(payload, validator):
    task = """Prepare recruiter interview prompts, not candidate evaluations. Return exactly four
questions with IDs profile-1, profile-2, profile-3 (kind profile) and clarification (kind clarification).
Use only the supplied requirement-linked evidence. Each profile question must cite at least one
supplied exact source reference and a relevant requirement ID. Ask about implementation choices,
responsibilities, testing or outcomes actually described; never invent a project, achievement,
responsibility, date or outcome. Clarification must address the supplied clarification_requirement_id,
using cautious wording: absent supporting evidence is something to explore, never proof of inability
or dishonesty. Its source_refs can be empty for an absent requirement. Include a concise purpose
and optional follow_up (empty string when unnecessary). No fabricated assertions in question premises,
accusations, morality verdicts, private beliefs, protected traits, numeric values score or hiring decision.
The recruiter will ask the questions in their normal interview. Do not invent answers or assess character.
Two standard situational questions are appended by the server; do not generate them."""
    return generate(GuideOutput, task, payload, validator)

def generate_candidate_feedback(application,reason):
    payload={'job':application.job.title,'requirements':requirement_data(application.job),'matches':application.breakdown,'claims':application.analysis.get('claims',[]),'recruiter_reason':reason}
    return generate(FeedbackOutput,'Draft respectful specific constructive SWOT feedback and a short email under 1800 characters. Candidate-facing threats are role-specific challenges. Use only supplied evidence; absence is not inability. Give concrete actions. Never compare to other applicants unless recruiter explicitly supplies that fact. Do not repeat speculative contradiction allegations. No protected or personal judgments. Do not decide rejection: recruiter already decided.',payload)
