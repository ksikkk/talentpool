"""Local-only viewer; no outgoing HTTP or external API calls."""
import json, os, base64, hmac
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from receiver import connect_db

app=FastAPI(docs_url=None,redoc_url=None,title="Internal Talent Pool")

def guard(request:Request):
    pwd=os.getenv("INTERNAL_VIEW_PASSWORD")
    if not pwd: raise HTTPException(503,"INTERNAL_VIEW_PASSWORD is required")
    try:
        token=request.headers.get("authorization","").split(" ",1)[1]
        candidate=base64.b64decode(token).decode().split(":",1)[1]
        if hmac.compare_digest(candidate,pwd): return
    except Exception: pass
    raise HTTPException(401,"Login required",headers={"WWW-Authenticate":'Basic realm="Internal Talent Pool"'})

@app.get("/",response_class=HTMLResponse)
def index(_=Depends(guard)):
    return """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>사내 인재 Pool</title><style>body{font:16px sans-serif;background:#f5f7fa;max-width:900px;margin:25px auto;padding:16px}article{background:white;border:1px solid #ddd;border-radius:12px;margin:14px 0;padding:16px}input{padding:12px;width:92%;max-width:430px}a{word-break:break-all}</style><h1>사내 인재 Pool</h1><p>사내 로컬 DB 조회 · 외부 전송 기능 없음</p><input id="q" placeholder="이름 / 소속 / 연구 분야 검색"><div id="results"></div><script>async function load(){const r=await fetch('/api/talents?q='+encodeURIComponent(document.querySelector('#q').value));const d=await r.json();const root=document.querySelector('#results');root.replaceChildren();for(const t of d.items){const box=document.createElement('article');const title=document.createElement('h3');title.textContent=t.name+' · '+t.org;box.append(title);for(const field of ['headline','domain','summary','why_fit']){const p=document.createElement('p');p.textContent=t[field]||'';box.append(p)}for(const u of t.sources){try{const parsed=new URL(u);if(parsed.protocol==='https:'){const a=document.createElement('a');a.href=parsed.href;a.textContent=parsed.hostname+' (공개 근거)';a.target='_blank';a.rel='noopener noreferrer';box.append(a,document.createElement('br'))}}catch{}}root.append(box)}}document.querySelector('#q').oninput=load;load()</script></html>"""

@app.get("/api/talents")
def talents(q:str="",_=Depends(guard)):
    db=connect_db(os.getenv("INTERNAL_DB_PATH","./internal_talents.db"))
    try:
        rows=db.execute("SELECT * FROM talent WHERE name LIKE ? OR org LIKE ? OR domain LIKE ? ORDER BY updated_at DESC LIMIT 300",("%"+q[:80]+"%",)*3).fetchall()
        return {"items":[{**dict(row),"sources":json.loads(row["sources_json"])} for row in rows]}
    finally: db.close()
