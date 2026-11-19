"""One-off, operator-approved internal candidate mail.

Uses the existing Knox adapter, approval secret and contact history. A temporary
recipient is NEVER written to the candidate's profile.
"""
import html
import sqlite3
import uuid
from datetime import datetime, timezone
from followup_service import check_approval, config, email_address, send_knox, today
from management import add_contact, get_talent, list_talents

def available(db, q):
    """Server-side search, not the 500-row dashboard subset."""
    q=(q or "").strip()
    if not q:
        return []
    if len(q)>100:
        raise ValueError("검색어는 100자 이하로 입력하세요.")
    people=list_talents(db,q=q,limit=60)
    return [{
        "id":t["id"],"name":t["name"],"org":t["org"],"headline":t["headline"],
        "domain":t["domain"],"email":t["email"],"status":t["status"],"priority":t["priority"],
    } for t in people]

def draft(db, talent_id):
    t=get_talent(db,talent_id)
    if not t:
        raise ValueError("선택한 인재가 존재하지 않습니다.")
    if t["status"] in ("보류","종료"):
        raise ValueError("보류 또는 종료 상태의 인재는 일반 메일 발송 대상에서 제외됩니다.")
    return {
        "talent_id":talent_id,"name":t["name"],"org":t["org"],"headline":t["headline"],
        "recipient":t.get("email") or "",
        "subject":"안녕하세요, "+t["name"]+"님.",
        "body":t["name"]+"님, 안녕하세요.\n\n연락드리게 되어 반갑습니다.\n\n감사합니다.",
        "request_id":str(uuid.uuid4()),
    }

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS direct_mail_send (
        request_id TEXT PRIMARY KEY,
        talent_id INTEGER NOT NULL,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        state TEXT NOT NULL,
        attempted_at TEXT NOT NULL
    )""")
    db.commit()

def send(db, talent_id, values):
    """A single explicit send attempt; 2xx -> contact history, unknown -> no contact."""
    if not isinstance(values,dict):
        raise ValueError("메일 발송 항목을 확인하세요.")
    check_approval(values.get("approval_code",""))
    person=get_talent(db,talent_id)
    if not person:
        raise ValueError("선택한 인재가 존재하지 않습니다.")
    if person["status"] in ("보류","종료"):
        raise ValueError("보류 또는 종료 상태의 인재는 메일을 발송할 수 없습니다.")
    recipient=email_address(values.get("recipient",""))
    subject=values.get("subject")
    body=values.get("body")
    rid=values.get("request_id")
    try:
        if str(uuid.UUID(rid))!=rid or len(rid)!=36:
            raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise ValueError("메일 작성창을 다시 열어주세요.") from None
    if not isinstance(subject,str) or not subject.strip() or len(subject)>300:
        raise ValueError("메일 제목을 확인하세요.")
    if not isinstance(body,str) or not body.strip() or len(body)>15000:
        raise ValueError("메일 본문을 확인하세요.")
    # Load configuration before locking in the request id: allow missing config
    # to be corrected without an ambiguous transport attempt.
    c=config()
    init(db)
    now=datetime.now(timezone.utc).isoformat()
    try:
        with db:
            db.execute("""INSERT INTO direct_mail_send
                (request_id,talent_id,recipient,subject,state,attempted_at)
                VALUES(?,?,?,?,?,?)""",
                (rid,talent_id,recipient,subject.strip(),"sending",now))
    except sqlite3.IntegrityError:
        raise ValueError("이미 발송을 시도한 요청입니다. 발신함에서 결과를 확인한 뒤 새 메일을 작성하세요.") from None
    escaped=html.escape(body).replace("\n","<br>")
    contents="<html><body><div style='font-family:Arial,sans-serif;line-height:1.7'>"+escaped+"</div></body></html>"
    try:
        result=send_knox(c,recipient,subject,contents,rid)
    except ValueError:
        with db:
            db.execute("UPDATE direct_mail_send SET state='uncertain' WHERE request_id=?",(rid,))
        raise
    with db:
        db.execute("UPDATE direct_mail_send SET state='accepted' WHERE request_id=?",(rid,))
        add_contact(db,talent_id,"이메일",subject.strip(),
            "사내 메일쓰기 기능으로 API 발송 요청 승인 / 수신자: "+recipient+" / 요청ID: "+rid,
            today().isoformat())
    return result
