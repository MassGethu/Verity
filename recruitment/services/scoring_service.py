import re
from datetime import date
VALUES = {'strong':1.0, 'moderate':.75, 'weak':.4, 'mentioned':.25, 'missing':0.0}
ALIASES = {'postgres':'postgresql', 'js':'javascript', 'python3':'python', 'py':'python', 'nodejs':'node.js'}
PARENTS = {'python': {'django','flask','fastapi'}, 'sql': {'postgresql','mysql','sqlite'}}
def canonical(value):
    value = value.strip().lower()
    return ALIASES.get(value, value)
def relevant_months(experiences, today):
    intervals = []
    for exp in experiences:
        if exp.get('date_precision') != 'month': continue
        start, end = exp.get('start_date'), exp.get('end_date')
        if not start or not re.fullmatch(r'\d{4}-\d{2}', start): continue
        if end == 'present': end = today.strftime('%Y-%m')
        if not end or not re.fullmatch(r'\d{4}-\d{2}', end): continue
        try:
            sy, sm = map(int, start.split('-')); ey, em = map(int, end.split('-'))
            date(sy,sm,1); date(ey,em,1)
        except ValueError: continue
        a, b = sy*12+sm, ey*12+em
        b = min(b, today.year*12+today.month)
        if b >= a: intervals.append((a,b))
    merged=[]
    for a,b in sorted(intervals):
        if merged and a <= merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else: merged.append((a,b))
    return sum(b-a for a,b in merged)
def calculate(requirements, analysis, today=None):
    today = today or date.today()
    matches={m['requirement_id']:m for m in analysis['requirement_matches']}
    candidate=analysis['candidate']; projects={p['id']:p for p in candidate['projects']}; exps={e['id']:e for e in candidate['experience']}
    rows=[]; total=earned=coverage=0; cats={}; project_ids=set(); exp_ids=set()
    for req in requirements:
        m=matches[req['id']]; value=VALUES[m['evidence_level']]
        if m['relevance']=='related': value=min(value,.4)
        w=req['weight']*(2 if req['essential'] else 1)
        qualifying=m['relevance']=='direct' and value>=.75
        pids={p for p in m['relevant_project_ids'] if p in projects} if qualifying else set()
        eids={e for e in m['relevant_experience_ids'] if e in exps} if qualifying else set()
        months=relevant_months([exps[e] for e in eids],today)
        attainment=1
        if req.get('minimum_months'): attainment=min(months/req['minimum_months'],1)
        if req.get('minimum_count'): attainment=min(len(pids)/req['minimum_count'],1)
        match=value*attainment; contribution=w*match
        rows.append({**m,'label':req['label'],'category':req['category'],'essential':req['essential'],'weight':w,'attainment':attainment,'match':match,'contribution':contribution,'months':months,'projects':len(pids),'gap':req['essential'] and match<.75})
        total+=w; earned+=contribution; coverage+=w if qualifying else 0
        cat=cats.setdefault(req['category'],[0,0]); cat[0]+=contribution; cat[1]+=w
        project_ids.update(pids); exp_ids.update(eids)
    return {'overall':100*earned/total if total else 0,'coverage':100*coverage/total if total else 0,'categories':{k:100*a/b for k,(a,b) in cats.items()},'rows':rows,'essential_gaps':sum(r['gap'] for r in rows),'project_count':len(project_ids),'experience_months':relevant_months([exps[e] for e in exp_ids],today),'total_weight':total}
