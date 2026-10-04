import re
import calendar
from datetime import date
from .scoring_service import canonical, ALIASES, PARENTS, relevant_months

def validate_analysis(output, blocks, requirements, today):
    data=output.model_dump(); sources={b['id']:b['text'] for b in blocks}
    def check(refs, required=False):
        if required and not refs: raise ValueError('Supporting citations are required.')
        for ref in refs:
            if not ref['exact_quote'].strip() or ref['exact_quote'] not in sources.get(ref['block_id'],''): raise ValueError('AI returned an invalid source quote.')
    def contains(text,key):
        variants={key}|{a for a,b in ALIASES.items() if b==key}
        return any(re.search(r'(?<!\w)'+re.escape(v)+r'(?!\w)',text,re.I) for v in variants)
    c=data['candidate']; structured=[]
    for kind in ['projects','experience','education','certifications']:
        for item in c[kind]: check(item['source_refs'],True); structured.extend(item['source_refs'])
    for kind in ['projects','experience']:
        items=c[kind]
        if len({x['id'] for x in items})!=len(items): raise ValueError('Duplicate evidence IDs.')
    # The same source excerpt cannot become multiple counted projects.
    seen=set(); remap={}; unique=[]
    for p in c['projects']:
        signature=tuple(sorted((r['block_id'],r['exact_quote']) for r in p['source_refs']))
        if signature in seen:
            old=next(x for x in unique if tuple(sorted((r['block_id'],r['exact_quote']) for r in x['source_refs']))==signature)
            remap[p['id']]=old['id']
        else: seen.add(signature); unique.append(p)
    c['projects']=unique
    pmap={p['id']:p for p in c['projects']}; emap={e['id']:e for e in c['experience']}
    for e in c['experience']:
        quoted=' '.join(r['exact_quote'] for r in e['source_refs']).lower()
        for key in ['start_date','end_date']:
            v=e.get(key)
            if v and v!='present' and not re.fullmatch(r'\d{4}(-\d{2})?',v): raise ValueError('Invalid experience date.')
        if e['start_date']=='present': raise ValueError('Invalid start date.')
        if e['date_precision']=='month':
            for key in ['start_date','end_date']:
                v=e.get(key)
                if v and v!='present':
                    if not re.fullmatch(r'\d{4}-\d{2}',v) or not 1<=int(v[-2:])<=12: raise ValueError('Invalid month date.')
                    year,month=map(int,v.split('-')); date(year,month,1)
                    patterns=[v, f'{month:02d}/{year}',f'{month}/{year}',f'{calendar.month_abbr[month].lower()} {year}',f'{calendar.month_name[month].lower()} {year}',f'{calendar.month_abbr[month].lower()}, {year}',f'{calendar.month_name[month].lower()}, {year}']
                    if not any(x in quoted for x in patterns): raise ValueError('Experience date has no quoted support.')
                elif v=='present' and not any(x in quoted for x in ['present','current','ongoing']): raise ValueError('Current experience has no quoted support.')
            if e.get('start_date') and e.get('end_date') and e['end_date']!='present' and e['end_date']<e['start_date']: raise ValueError('Experience dates are reversed.')
    ids=[m['requirement_id'] for m in data['requirement_matches']]
    if len(ids)!=len(set(ids)) or set(ids)!={r['id'] for r in requirements}: raise ValueError('Incomplete requirement coverage.')
    for m in data['requirement_matches']:
        check(m['source_refs'],m['evidence_level']!='missing')
        m['relevant_project_ids']=list(dict.fromkeys(remap.get(p,p) for p in m['relevant_project_ids']))
        if any(p not in pmap for p in m['relevant_project_ids']) or any(e not in emap for e in m['relevant_experience_ids']): raise ValueError('Unknown evidence ID.')
        linked=[pmap[p] for p in m['relevant_project_ids']]+[emap[e] for e in m['relevant_experience_ids']]
        linked_refs=[r for x in linked for r in x['source_refs']]
        credential_refs=[r for x in c['education']+c['certifications'] for r in x['source_refs']]
        backed=any(r in linked_refs+credential_refs for r in m['source_refs'])
        if m['evidence_level'] in ['strong','moderate','weak'] and not backed: m['evidence_level']='mentioned'
        if m['relevance']=='absent': m['evidence_level']='missing'; m['source_refs']=[]
        req=next(r for r in requirements if r['id']==m['requirement_id'])
        key=canonical(req['canonical_key'])
        linked_text=' '.join(r['exact_quote'] for r in linked_refs+[r for r in m['source_refs'] if r in credential_refs])
        if req['category']=='skills' and backed:
            explicit=contains(linked_text,key)
            parent=any(contains(linked_text,t) for t in PARENTS.get(key,set()))
            if not explicit and parent:
                m['relevance']='direct'
                if m['evidence_level']=='strong': m['evidence_level']='moderate'
            elif not explicit and m['relevance']=='direct':
                if any(contains(r['exact_quote'],key) for r in m['source_refs']): m['evidence_level']='mentioned'
                else: m['evidence_level']='missing'; m['relevance']='absent'; m['source_refs']=[]
        if req['category']=='education' and m['evidence_level'] in ['strong','moderate'] and not any(r in credential_refs for r in m['source_refs']): m['evidence_level']='mentioned'
    claims={x['id']:x for x in data['claims']}
    if len(claims)!=len(data['claims']): raise ValueError('Duplicate claims.')
    for claim in data['claims']:
        check(claim['source_refs'],True); check(claim['supporting_refs'])
        if claim['support_level'] in ['strong','moderate','weak'] and not any(r in structured for r in claim['supporting_refs']): claim['support_level']='mentioned'
        if any(e not in emap for e in claim['relevant_experience_ids']): raise ValueError('Unknown claim experience.')
        claimed=claim['claimed_months']; refs=claim['source_refs']
        # Duration must be explicitly quoted; never infer it from a vague seniority label.
        explicit=[]
        for r in refs:
            for amount,unit in re.findall(r'(\d+(?:\.\d+)?)\s*(years?|months?)',r['exact_quote'],re.I): explicit.append(round(float(amount)*(12 if unit.lower().startswith('year') else 1)))
        if claimed and claimed in explicit and claim['relevant_experience_ids']:
            experiences=[emap[e] for e in claim['relevant_experience_ids']]
            precise=all(e['date_precision']=='month' and e['start_date'] and e['end_date'] for e in experiences)
            months=relevant_months(experiences,today)
            if precise and claimed-months>=12:
                data['review_flags'].append({'claim_id':claim['id'],'type':'duration_evidence_gap','claim_refs':refs,'evidence_refs':[r for e in experiences for r in e['source_refs']],'explanation':f'The resume claims {claimed} months; dated relevant entries show about {months} months. Earlier or undated experience may be omitted. Recruiter review recommended.'})
    for flag in data['review_flags']:
        if flag['claim_id'] not in claims: raise ValueError('Unknown flagged claim.')
        check(flag['claim_refs'],True); check(flag['evidence_refs'],True)
        flag['manual_review_required']=True
    # External links must actually have been supplied, and use safe web protocols.
    raw='\n'.join(sources.values())
    if c['email'] and c['email'] not in raw: c['email']=None
    if c['name'] and c['name'].casefold() not in raw.casefold(): c['name']=None
    for key,url in c['supplied_links'].items():
        if url and (not url.startswith(('https://','http://')) or url not in raw): c['supplied_links'][key]=None
    return data
