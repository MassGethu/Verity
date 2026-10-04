import base64, os, re
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlparse, quote
import requests
from django.utils import timezone
from ..models import GitHubAnalysis
from .scoring_service import canonical

class GitHubError(Exception):
    def __init__(self,message,retry_at=None): super().__init__(message); self.retry_at=retry_at

def username_from_url(url,confirm_owner=False):
    parsed=urlparse(url or '')
    if parsed.scheme!='https' or parsed.netloc.lower()!='github.com' or parsed.query or parsed.fragment: raise GitHubError('Supply a valid https://github.com/username profile URL.')
    parts=[p for p in parsed.path.split('/') if p]
    if not parts or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?',parts[0]) or parts[0].lower() in {'settings','login','orgs','topics','search','marketplace','features','about','explore'}: raise GitHubError('Invalid GitHub profile URL.')
    if len(parts)>1 and not confirm_owner: raise GitHubError('This is a repository URL. Confirm that the owner is the candidate before inspecting this profile.')
    return parts[0]

def fetch_github(application,refresh=False,confirm_owner=False):
    url=application.candidate.get('supplied_links',{}).get('github')
    analysis,_=GitHubAnalysis.objects.get_or_create(application=application)
    try:
        username=username_from_url(url,confirm_owner)
        now=timezone.now()
        if analysis.username==username and analysis.fetched_at and now-analysis.fetched_at<timedelta(hours=24) and analysis.snapshot and not refresh: return analysis
        if analysis.retry_at and analysis.retry_at>now: raise GitHubError('GitHub rate limit is still active. Try after '+analysis.retry_at.isoformat(),analysis.retry_at)
        headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        if os.getenv('GITHUB_TOKEN'): headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
        session=requests.Session(); session.headers.update(headers)
        def get(path,optional=False):
            with session.get('https://api.github.com'+path,timeout=(3,6),allow_redirects=False,stream=True) as resp:
                if resp.status_code in (403,429):
                    reset=resp.headers.get('X-RateLimit-Reset'); retry=resp.headers.get('Retry-After')
                    retry_at=datetime.fromtimestamp(int(reset),dt_timezone.utc) if reset and reset.isdigit() else now+timedelta(seconds=int(retry) if retry and retry.isdigit() else 60)
                    raise GitHubError('GitHub access/rate limit reached. Cached evidence is retained.',retry_at)
                if resp.status_code==404:
                    if optional:return None
                    raise GitHubError('GitHub profile does not exist or is unavailable.')
                if resp.status_code!=200: raise GitHubError('GitHub request unavailable. Please retry later.')
                content=b''
                for chunk in resp.iter_content(65536):
                    content+=chunk
                    if len(content)>1024*1024: raise GitHubError('Repository response too large for bounded inspection.')
                import json
                return json.loads(content)
        try:
            user=get('/users/'+quote(username)); repos=get('/users/'+quote(username)+'/repos?per_page=30&sort=updated&type=owner')
            if user.get('type')!='User': raise GitHubError('An organization profile is not candidate identity evidence.')
            terms={canonical(r.canonical_key) for r in application.job.requirements.all()}
            def relevance(repo):
                text=(repo['name']+' '+(repo.get('description') or '')+' '+(repo.get('language') or '')).lower()
                return (sum(t in text for t in terms),repo.get('updated_at',''))
            chosen=sorted([r for r in repos if not r.get('fork')],key=relevance,reverse=True)[:3]
            evidence=[]; snapshots=[]
            for repo in chosen:
                owner=quote(username,safe=''); name=quote(repo['name'],safe=''); root=f'/repos/{owner}/{name}'
                languages=get(root+'/languages',True) or {}
                readme=get(root+'/readme',True) or {}
                try: text=base64.b64decode(readme.get('content','')).decode('utf-8',errors='replace')[:8000]
                except Exception: text=''
                contents=get(root+'/contents/',True) or []
                files=[f['name'] for f in contents] if isinstance(contents,list) else []
                signals=[]
                for language,count in languages.items():
                    if canonical(language) in terms: signals.append(f'Repository contains {language} ({count:,} bytes).')
                for term in terms:
                    if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I): signals.append(f'README mentions {term}; documentation is a self-reported repository claim.')
                if 'Dockerfile' in files: signals.append('Root Dockerfile found: container configuration evidence.')
                if 'manage.py' in files: signals.append('Root manage.py found: possible Django project structure; inspect source manually.')
                link='https://github.com/'+username+'/'+repo['name']
                evidence.append({'repository':repo['name'],'url':link,'description':repo.get('description') or '', 'signals':signals,'updated_at':repo.get('updated_at'),'readme_excerpt':text[:1200]})
                snapshots.append({'name':repo['name'],'languages':languages,'root_files':files,'readme':text,'updated_at':repo.get('updated_at')})
            analysis.username=username; analysis.snapshot={'profile':user.get('html_url'),'repos':snapshots,'listed_count':len(repos),'scope':'Up to 30 owned repositories listed; up to 3 non-fork repositories inspected. Root files only.'}; analysis.evidence=evidence; analysis.fetched_at=now; analysis.retry_at=None; analysis.fetch_status='complete'; analysis.error=''; analysis.save()
        finally: session.close()
    except (GitHubError,requests.RequestException,ValueError,KeyError) as exc:
        analysis.fetch_status='failed'; analysis.error=str(exc) if isinstance(exc,GitHubError) else 'GitHub could not be reached or returned unexpected data. Retry later.'; analysis.retry_at=getattr(exc,'retry_at',None); analysis.save()
    return analysis
