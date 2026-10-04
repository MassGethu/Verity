"""Explicit fixture interpreter. Never used as a fallback for live uploads.
Only supports the deliberately structured synthetic PDF records in demo/.
"""
import re
from ..schemas import ResumeOutput
from .evidence_service import validate_analysis
from .scoring_service import canonical, PARENTS

DEMO_REQUIREMENTS=[
 ('Python','python','skills',True,5,None,None),('Django','django','skills',True,5,None,None),('SQL','sql','skills',True,4,None,None),('Git','git','skills',False,3,None,None),('Docker','docker','skills',False,2,None,None),('Backend projects','backend projects','projects',True,5,None,2),('Backend experience','backend experience','experience',False,2,6,None),('Automated tests','automated tests','expectations',False,3,None,None)
]
DEMO_JD='''Backend Developer Intern
Essential: Python, Django, SQL and at least 2 backend projects.
Important: Git version control and automated tests.
Preferred: Docker and 6 months of backend experience.
Build maintainable APIs, communicate tradeoffs, and collaborate on code reviews.'''

def fixture_analysis(blocks,requirements,today):
    def refs(text): return [{'block_id':b['id'],'exact_quote':b['text']} for b in blocks if text in b['text']]
    name=next(b['text'] for b in blocks if b['text'].startswith('Candidate: ')).removeprefix('Candidate: ')
    email=next(b['text'] for b in blocks if b['text'].startswith('Email: ')).removeprefix('Email: ')
    skill_line=next(b['text'] for b in blocks if b['text'].startswith('Skills: ')); skills=skill_line.removeprefix('Skills: ').split(', ')
    projects=[]; experience=[]
    groups=[]
    for b in blocks:
        if any(b['text'].startswith(prefix) for prefix in ['Candidate: ','Email: ','Education: ','Skills: ','Claim: ','Project: ','Experience: ','GitHub: ','Synthetic ']):
            groups.append([b])
        elif groups: groups[-1].append(b)
    for group in groups:
        b={'text':' '.join(x['text'] for x in group)}
        group_refs=[{'block_id':x['id'],'exact_quote':x['text']} for x in group]
        if b['text'].startswith('Project: '):
            title,text=b['text'].removeprefix('Project: ').split(' | ',1)
            projects.append({'id':'p'+str(len(projects)+1),'title':title,'description':text,'technologies':[s for s in ['Python','Django','SQL','Git','Docker','automated tests'] if s.lower() in text.lower()],'source_refs':group_refs})
        if b['text'].startswith('Experience: '):
            role,org,start,end,text=b['text'].removeprefix('Experience: ').split(' | ',4)
            experience.append({'id':'e'+str(len(experience)+1),'role':role,'organization':org,'start_date':start,'end_date':end,'date_precision':'month','technologies':[s for s in ['Python','Django','SQL','Git','Docker'] if s.lower() in text.lower()],'source_refs':group_refs})
    links={k:None for k in ['github','linkedin','instagram','reddit','portfolio']}
    for b in blocks:
        if b['text'].startswith('GitHub: '):links['github']=b['text'].removeprefix('GitHub: ')
    candidate={'name':name,'email':email,'phone':None,'education':[{'description':'BSc Computer Science (synthetic)','source_refs':refs('Education: ')}],'skills':skills,'projects':projects,'experience':experience,'achievements':[],'certifications':[],'supplied_links':links}
    matches=[]; claims=[]
    for req in requirements:
        key=canonical(req['canonical_key'])
        if req['category']=='projects': selected=projects; selected_e=[]
        elif req['category']=='experience':selected=[];selected_e=experience
        else:
            selected=[p for p in projects if key in {canonical(t) for t in p['technologies']}]
            selected_e=[e for e in experience if key in {canonical(t) for t in e['technologies']}]
        # Only explicitly technical projects qualify for the backend requirement.
        if req['category']=='projects':selected=[p for p in selected if {'python','django'}<={canonical(t) for t in p['technologies']}]
        support=[r for item in selected+selected_e for r in item['source_refs']]
        mentioned=key in {canonical(s) for s in skills}
        if support:level='strong' if any('built' in r['exact_quote'].lower() or 'implemented' in r['exact_quote'].lower() for r in support) else 'moderate'; relevance='direct'; source=support
        elif mentioned:level='mentioned';relevance='direct';source=refs('Skills: ')
        else:level='missing';relevance='absent';source=[]
        matches.append({'requirement_id':req['id'],'relevance':relevance,'evidence_level':level,'source_refs':source,'relevant_project_ids':[p['id'] for p in selected],'relevant_experience_ids':[e['id'] for e in selected_e],'explanation':'Concrete use appears in the quoted project/work passages.' if support else ('Listed as a skill, with no additional project/work evidence.' if mentioned else 'No relevant supporting passage found.')})
        if mentioned:
            claims.append({'id':key,'text':req['label'],'canonical_key':key,'source_refs':refs('Skills: '),'supporting_refs':support,'support_level':level,'claimed_months':None,'relevant_experience_ids':[e['id'] for e in selected_e],'review_notes':[]})
    duration=refs('Claim: ')
    if duration:
        claims.append({'id':'python-duration','text':duration[0]['exact_quote'].removeprefix('Claim: '),'canonical_key':'python','source_refs':duration,'supporting_refs':[r for e in experience for r in e['source_refs']],'support_level':'moderate','claimed_months':36,'relevant_experience_ids':[e['id'] for e in experience],'review_notes':[]})
    output=ResumeOutput.model_validate({'candidate':candidate,'requirement_matches':matches,'claims':claims,'review_flags':[]})
    return validate_analysis(output,blocks,requirements,today)
