"""Private, local-only dashboard and CRUD API. No outbound requests."""
import os, ipaddress, socket
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, Body, Query
from fastapi.responses import HTMLResponse
from management import database, list_talents, get_talent, edit_talent, add_contact, contacts, delete_talent

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,title="Internal Talent Pool")

def _local_bindable_addresses():
    """People-style local address check, no external lookup or data transfer."""
    try:
        records=socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET,socket.SOCK_STREAM)
    except OSError:
        return set()
    addresses=set()
    for record in records:
        address=record[4][0]
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
                probe.bind((address,0))
            addresses.add(address)
        except OSError:
            pass
    return addresses


def guard(request: Request):
    """Shared intranet mode, same-origin and actual local Host check."""
    try:
        peer=ipaddress.ip_address(request.client.host if request.client else "")
    except ValueError:
        raise HTTPException(403,"Invalid client")
    if peer.is_loopback:
        return True
    if os.getenv("TALENTPOOL_SHARE_EDIT") != "1":
        raise HTTPException(403,"Shared mode is disabled")
    host=request.headers.get("host","")
    if len(request.headers.getlist("host")) != 1:
        raise HTTPException(403,"Invalid Host header")
    expected={f"{a}:8090" for a in _local_bindable_addresses()}
    # In shared mode, ASGI server may report the accepted socket's actual
    # local IPv4 even when the listening socket is bound to 0.0.0.0.
    server=request.scope.get("server") or ()
    if len(server)>=2:
        try:
            local=ipaddress.ip_address(server[0])
            if local.version==4 and not local.is_unspecified:
                expected.add(f"{local}:{server[1]}")
        except ValueError:
            pass
    if host not in expected:
        raise HTTPException(403,"Use this PC's actual IPv4 address and port")
    origin=request.headers.get("origin")
    if origin and origin != f"http://{host}":
        raise HTTPException(403,"Origin mismatch")
    if request.headers.get("sec-fetch-site")=="cross-site":
        raise HTTPException(403,"Cross-site requests not accepted")
    return True


def write_guard(request:Request, _=Depends(guard)):
    if request.headers.get("X-Internal-Action")!="1":
        raise HTTPException(403,"Action header missing")
    origin=request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit
        try:
            o=urlsplit(origin)
            if o.scheme!=request.url.scheme or o.netloc!=request.headers.get("host",""):
                raise HTTPException(403,"Origin mismatch")
        except ValueError: raise HTTPException(403,"Invalid origin")
    return _

@app.get("/",response_class=HTMLResponse)
def index(_=Depends(guard)):
    return Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")

@app.get("/api/talents")
def talents(q:str="",status:str="",priority:str="",domain:str="",limit:int=Query(200,ge=1,le=500),_=Depends(guard)):
    db=database()
    try:
        return {"items":list_talents(db,q=q,status=status,priority=priority,domain=domain,limit=limit)}
    finally: db.close()

@app.get("/api/talents/{talent_id}")
def detail(talent_id:int,_=Depends(guard)):
    db=database()
    try:
        result=get_talent(db,talent_id)
        if not result: raise HTTPException(404,"Talent not found")
        return result
    finally: db.close()

@app.patch("/api/talents/{talent_id}")
def update(talent_id:int, changes:dict=Body(...),_=Depends(write_guard)):
    db=database()
    try:
        try: result=edit_talent(db,talent_id,changes)
        except ValueError as e: raise HTTPException(422,str(e))
        if not result: raise HTTPException(404,"Talent not found")
        return result
    finally: db.close()

@app.get("/api/talents/{talent_id}/contacts")
def history(talent_id:int,_=Depends(guard)):
    db=database()
    try:
        if not get_talent(db,talent_id): raise HTTPException(404,"Talent not found")
        return {"items":contacts(db,talent_id)}
    finally: db.close()

@app.post("/api/talents/{talent_id}/contacts")
def create_contact(talent_id:int, entry:dict=Body(...),_=Depends(write_guard)):
    required={"contact_at","channel","subject","memo"}
    if set(entry)!=required: raise HTTPException(422,"Invalid contact fields")
    db=database()
    try:
        try:
            new_id=add_contact(db,talent_id,**entry)
        except (ValueError,TypeError): raise HTTPException(422,"Invalid contact values")
        if new_id is None: raise HTTPException(404,"Talent not found")
        return {"id":new_id}
    finally: db.close()

@app.delete("/api/talents/{talent_id}")
def delete_candidate(talent_id:int,_=Depends(write_guard)):
    db=database()
    try:
        if not delete_talent(db,talent_id):
            raise HTTPException(404,"Talent not found")
        return {"deleted":True}
    finally: db.close()

@app.get("/api/monthly-reviews")
def monthly_reviews(_=Depends(guard)):
    from refresh_receiver import create_refresh_table
    db=database()
    try:
        create_refresh_table(db)
        rows=db.execute("""SELECT id,batch_id,candidate_name,previous_org,field,
            old_value,proposed_value,evidence_url,evidence_excerpt,reason,status,created_at
            FROM pending_refresh ORDER BY created_at DESC,id DESC LIMIT 500""").fetchall()
        return {"items":[dict(row) for row in rows]}
    finally:
        db.close()

@app.get("/monthly-reviews",response_class=HTMLResponse)
def monthly_review_page(_=Depends(guard)):
    return Path(__file__).with_name("monthly_reviews.html").read_text(encoding="utf-8")
