"""Intranet talent dashboard and CRUD API with opt-in internal Knox mail."""
import os, ipaddress, socket, threading, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, Body, Query
from fastapi.responses import HTMLResponse
from management import database, list_talents, get_talent, edit_talent, add_contact, contacts, delete_talent

_mail_state={"enabled":False,"last_poll":None,"last_counts":None,"last_error":None}

@asynccontextmanager
async def lifespan(application):
    stop=threading.Event()
    required=("POP3_USER","POP3_PASSWORD","TRUSTED_SENDER","HANDOFF_SECRET")
    configured=all(os.getenv(k) for k in required)
    _mail_state["enabled"]=configured
    if not configured:
        print("[Talent Pool] Automatic mail import disabled: set POP3_USER, POP3_PASSWORD, TRUSTED_SENDER and HANDOFF_SECRET locally.")
    def loop():
        from datetime import datetime, timezone
        from receiver import poll_once
        interval=max(60,int(os.getenv("POP3_POLL_SECONDS","300")))
        while not stop.is_set():
            try:
                summary=poll_once()
                _mail_state.update(last_poll=datetime.now(timezone.utc).isoformat(),
                                   last_counts=summary,last_error=None)
                print("[Talent Pool] Auto mail import: "+
                      str(summary.get("imported",0))+" imported, "+
                      str(summary.get("duplicate",0))+" duplicate.")
            except Exception as exc:
                _mail_state["last_error"]=type(exc).__name__
                print("[Talent Pool] Auto mail import failed: "+type(exc).__name__)
            if stop.wait(interval): break
    worker=None
    if configured:
        worker=threading.Thread(target=loop,daemon=True,name="talentpool-mail-poller")
        worker.start()
    followup_thread=None
    if os.getenv("FOLLOWUP_NOTIFY_ENABLED")=="1":
        def followup_loop():
            from followup_service import notify_due
            from management import database
            while not stop.is_set():
                try:
                    db=database()
                    try:
                        result=notify_due(db)
                        print("[Talent Pool] Follow-up reminder scan: "+str(result.get("sent",0))+" API accepted.")
                    finally: db.close()
                except Exception as exc:
                    print("[Talent Pool] Follow-up reminder scan failed: "+type(exc).__name__)
                if stop.wait(24*60*60):break
        followup_thread=threading.Thread(target=followup_loop,daemon=True,name="talentpool-followup-notifier")
        followup_thread.start()
    try:
        yield
    finally:
        stop.set()
        if worker: worker.join(timeout=3)
        if followup_thread: followup_thread.join(timeout=3)

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,title="Internal Talent Pool",lifespan=lifespan)

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

@app.get("/api/mail-status")
def mail_status(_=Depends(guard)):
    return dict(_mail_state)

@app.get("/api/duplicate-reviews")
def duplicate_review_items(_=Depends(guard)):
    from duplicate_review import pending
    db=database()
    try:
        return {"items":pending(db)}
    finally:
        db.close()


@app.post("/api/duplicate-reviews/{review_id}")
def review_duplicate(review_id:int,decision:dict=Body(...),_=Depends(write_guard)):
    from duplicate_review import resolve
    if set(decision)!={"decision"} or decision["decision"] not in ("same","distinct"):
        raise HTTPException(422,"Select same or distinct")
    db=database()
    try:
        if not resolve(db,review_id,decision["decision"]):
            raise HTTPException(404,"Review not found")
        return {"resolved":decision["decision"]}
    finally:
        db.close()


@app.get("/duplicate-reviews",response_class=HTMLResponse)
def duplicate_review_page(_=Depends(guard)):
    return Path(__file__).with_name("duplicates.html").read_text(encoding="utf-8")

@app.get("/followups",response_class=HTMLResponse)
def followup_page(_=Depends(guard)):
    return Path(__file__).with_name("followups.html").read_text(encoding="utf-8")

@app.get("/api/followups")
def followup_list(_=Depends(guard)):
    from followup_service import notices
    db=database()
    try:
        items=notices(db)
        return {"items":items,"enabled":os.getenv("FOLLOWUP_NOTIFY_ENABLED")=="1"}
    finally: db.close()

@app.get("/api/followups/{talent_id}/draft")
def followup_draft(talent_id:int,_=Depends(guard)):
    from followup_service import draft
    db=database()
    try:
        try:return draft(db,talent_id)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
    finally:db.close()

@app.post("/api/followups/{talent_id}/send")
def followup_send(talent_id:int,changes:dict=Body(...),_=Depends(write_guard)):
    from followup_service import send_candidate
    required={"recipient","subject","body","approval_code","request_id"}
    if set(changes)!=required:raise HTTPException(422,"발송 필드를 확인하세요.")
    db=database()
    try:
        try:return send_candidate(db,talent_id,changes)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
    finally:db.close()

@app.get("/api/followups/settings")
def followup_settings(_=Depends(guard)):
    from followup_service import public_mail_settings
    try:return public_mail_settings()
    except ValueError as exc:raise HTTPException(422,str(exc)) from None


@app.patch("/api/followups/settings")
def followup_settings_save(changes:dict=Body(...),_=Depends(write_guard)):
    from followup_service import save_mail_addresses
    if set(changes)!={"sender","notify_email","approval_code"}:
        raise HTTPException(422,"메일 설정 필드를 확인하세요.")
    try:return save_mail_addresses(**changes)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None


