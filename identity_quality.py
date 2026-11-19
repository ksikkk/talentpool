"""Public-source identity signals and citation coverage. No network calls."""
import re
import unicodedata
from urllib.parse import urlparse,parse_qs,unquote

def norm(s):
    return ' '.join(unicodedata.normalize('NFKC',str(s or '')).casefold().split())

def url_key(url):
    try:
        p=urlparse(str(url))
        if p.scheme!='https' or not p.hostname or p.username or p.password:return ''
        host=p.hostname.lower().removeprefix('www.')
        path=unquote(p.path).rstrip('/').lower()
        if host in {'scholar.google.com','scholar.google.co.kr'} and path=='/citations':
            user=parse_qs(p.query).get('user',[''])[0]
            return 'scholar.google.com/citations?user='+user if user else ''
        return host+path
    except (ValueError,AttributeError):return ''

def profile_ids(sources):
    found=set()
    for url in sources:
        key=url_key(url)
        if re.fullmatch(r'orcid.org/\d{4}-\d{4}-\d{4}-[\dX]{4}',key,re.I):
            found.add('orcid:'+key.split('/',1)[1].upper())
        elif key.startswith('scholar.google.com/citations?user='):
            found.add('scholar:'+key.split('user=',1)[1])
        elif re.fullmatch(r'linkedin.com/in/[^/]+',key):
            found.add('linkedin:'+key.split('/in/',1)[1])
        elif re.fullmatch(r'researchgate.net/profile/[^/]+',key):
            found.add('researchgate:'+key.split('/profile/',1)[1])
    return found

def kinds(url):
    p=urlparse(url);host=(p.hostname or '').lower().removeprefix('www.');path=p.path.lower()
    if host=='orcid.org':return '연구자 식별정보'
    if host in ('scholar.google.com','scholar.google.co.kr'):return '학술 프로필'
    if host in ('doi.org','dx.doi.org','crossref.org','pubmed.ncbi.nlm.nih.gov') or '/doi/' in path:return '논문/DOI'
    if host.endswith(('.edu','.ac.kr','.edu.au','.ac.uk')) or '.ac.' in host:return '교육·연구기관 도메인'
    if host in ('linkedin.com','researchgate.net'):return '전문 프로필'
    if host.endswith(('.gov','.go.kr','.gov.uk')):return '공공기관 도메인'
    return '기타 공개 페이지'

def evidence_quality(person):
    sources=list(dict.fromkeys(u for u in person.get('sources',[]) if url_key(u)))
    types=[kinds(u) for u in sources]
    ident=bool(profile_ids(sources))
    institution=any(t in ('교육·연구기관 도메인','공공기관 도메인') for t in types)
    publication=any(t in ('논문/DOI','학술 프로필') for t in types)
    grade='근거 풍부' if ident and (institution or publication) else '근거 일부' if (ident or institution or publication) else '추가 검증 필요'
    return {'grade':grade,'sources':[{'url':u,'kind':kinds(u)} for u in sources],
            'note':'URL 종류를 자동 분류한 것이며 내용·동일 인물 여부의 최종 검증을 뜻하지 않습니다.'}

def compare_profiles(a,b):
    same_name=bool(norm(a.get('name'))) and norm(a.get('name'))==norm(b.get('name'))
    a_ids=profile_ids(a.get('sources',[]));b_ids=profile_ids(b.get('sources',[]))
    if a_ids & b_ids:
        return 'confirmed_id' if same_name else 'review', '동일 연구자 식별자 / 성명 일치 여부 확인'
    if same_name and norm(a.get('org')) and norm(a.get('org'))==norm(b.get('org')):
        if a_ids and b_ids and a_ids.isdisjoint(b_ids):
            return 'review','이름·소속 같지만 프로필 ID가 다름'
        a_urls={url_key(x) for x in a.get('sources',[]) if url_key(x)}
        b_urls={url_key(x) for x in b.get('sources',[]) if url_key(x)}
        if a_urls and a_urls==b_urls and norm(a.get('headline'))==norm(b.get('headline')):
            return 'exact_record','기존 인재 기록의 이름·소속·직책·출처가 동일'
        return 'review','이름·소속만 일치해 동명이인 가능'
    return 'distinct','중복 단서 없음'
