"""Private, local-only dashboard and CRUD API. No outbound requests."""
import os, ipaddress
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, Body, Query
from fastapi.responses import HTMLResponse
from management import database, list_talents, get_talent, edit_talent, add_contact, contacts, delete_talent

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,title="Internal Talent Pool")

def guard(request: Request):
    """No application password. Restrict by direct TCP source IP, fail closed by default."""
    ip = request.client.host if request.client else ""
    try:
        peer=ipaddress.ip_address(ip)
        configured=os.getenv("INTERNAL_ALLOWED_CIDRS","").strip()
        networks=[ipaddress.ip_network(x.strip(),strict=False)
                  for x in configured.split(",") if x.strip()]
        # Deny public or overly broad network configuration.
        networks=[net for net in networks if net.is_private and net.prefixlen >= (16 if net.version==4 else 64)]
        if peer.is_loopback or any(peer in network for network in networks):
            return True
    except ValueError:
        pass
    raise HTTPException(403,"This device is not in the approved internal network")

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
