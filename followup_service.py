"""Opt-in six-month follow-up reminders using the internal Knox mail API.

No mail is sent on import. Notification and candidate messages have separate
approval policies; failed/uncertain attempts are never silently retried.
"""
import calendar
import hashlib
import html
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urlencode, unquote_plus

CONFIG = Path(__file__).resolve().with_name("followup_mail.local.json")
EMAIL = re.compile(r"^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$")


def email_address(s):
    if not isinstance(s, str) or len(s) > 254 or not EMAIL.fullmatch(s):
        raise ValueError("메일 주소를 확인하세요.")
    return s


def today():
    return date.today()


def add_months(day, n=6):
    y = day.year + (day.month - 1 + n) // 12
    m = (day.month - 1 + n) % 12 + 1
    return date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def config():
    try:
        c = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ValueError("followup_mail.local.json을 설정하세요.") from None
    for key in ("knox_api_url", "Authorization", "System-ID", "sender", "notify_email"):
        if not isinstance(c.get(key), str) or not c[key].strip():
            raise ValueError("메일 설정 오류: " + key)
    email_address(c["sender"])
    email_address(c["notify_email"])
    url = urlsplit(c["knox_api_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Knox 메일 API는 HTTPS 주소를 입력하세요.")
    verify=c.get("verify_tls",True)
    if type(verify) is not bool and not (isinstance(verify,str) and bool(verify.strip())):
        raise ValueError("verify_tls는 true, false 또는 CA 인증서 경로만 허용합니다.")
    return c



def public_mail_settings():
    """Never expose Authorization, System-ID, API URL, or other secrets."""
    existing=CONFIG.exists()
    try:
        values=json.loads(CONFIG.read_text(encoding="utf-8-sig")) if existing else {}
    except (OSError,ValueError):
        raise ValueError("메일 설정 파일 형식을 확인하세요.") from None
    return {"configured":existing,
            "sender":values.get("sender",""),
            "notify_email":values.get("notify_email",""),
            "approval_required":False}


def save_mail_addresses(sender,notify_email):
    """Edit only two addresses; retain all Knox API secrets in the local file."""
    sender=email_address(sender)
    notify_email=email_address(notify_email)
    if not sender.lower().endswith("@samsung.com") or not notify_email.lower().endswith("@samsung.com"):
        raise ValueError("발신자 및 알림 수신자는 승인된 사내 @samsung.com 주소만 사용하세요.")
    if not CONFIG.exists():
        raise ValueError("followup_mail.local.json 파일이 없습니다. 예시 파일을 복사하여 사내 Knox API 정보를 먼저 설정하세요.")
    try:
        values=json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except (OSError,ValueError):
        raise ValueError("메일 설정 파일을 읽을 수 없습니다.") from None
    if not isinstance(values,dict):
        raise ValueError("메일 설정 파일 형식이 올바르지 않습니다.")
    values["sender"]=sender
    values["notify_email"]=notify_email
    # Same-directory atomic replace avoids partial JSON during scanner reads.
    import tempfile
    path=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=CONFIG.parent,
                prefix=".followup_mail_",suffix=".tmp",delete=False) as stream:
            path=Path(stream.name)
            json.dump(values,stream,ensure_ascii=False,indent=2)
            stream.write("\n")
        os.replace(str(path),str(CONFIG))
    finally:
        if path is not None and path.exists():
            path.unlink()
    return {"configured":True,"sender":sender,"notify_email":notify_email}


def configure_proxy():
    values=["openapi.samsung.net"]
    for name in ("NO_PROXY", "no_proxy"):
        for v in os.getenv(name, "").split(","):
            v=v.strip()
            if v and v.lower() not in {x.lower() for x in values}:
                values.append(v)
    os.environ["NO_PROXY"] = ",".join(values)
    os.environ["no_proxy"] = os.environ["NO_PROXY"]


def api_url(base, sender):
    u=urlsplit(base)
    query=[p for p in u.query.split("&") if p and unquote_plus(p.split("=", 1)[0]).lower() != "userid"]
    query.append(urlencode({"userId": sender.split("@", 1)[0]}))
    return urlunsplit((u.scheme, u.netloc, u.path, "&".join(query), u.fragment))


def send_knox(c, recipient, subject, body_html, request_id):
    """One HTTP request; 2xx indicates API acceptance, not delivery confirmation."""
    import requests
    recipient=email_address(recipient)
    sender=email_address(c["sender"])
    if not 0 < len(subject.strip()) <= 300 or not 0 < len(body_html) <= 150000:
        raise ValueError("메일 제목 또는 본문이 올바르지 않습니다.")
    payload={"subject":subject.strip(), "docSecuType":"PERSONAL",
             "contents":body_html,"contentType":"HTML",
             "sender":{"emailAddress":sender},
             "recipients":[{"emailAddress":recipient,"recipientType":"TO"}]}
    configure_proxy()
    try:
        response=requests.post(api_url(c["knox_api_url"],sender),
            headers={"accept":"*/*","Content-Type":"application/json",
                     "Authorization":c["Authorization"],"System-ID":c["System-ID"]},
            data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
            verify=c.get("verify_tls",True),timeout=(10,60),allow_redirects=False)
    except requests.RequestException:
        raise ValueError("메일 API 연결/응답 오류. 전송 여부를 메일함에서 확인하세요. 자동 재시도하지 않습니다.") from None
    if not 200 <= response.status_code < 300:
        raise ValueError("메일 API 오류 HTTP "+str(response.status_code)+". 전송 여부를 확인하세요.")
    return {"status":"api_accepted","http_status":response.status_code,
            "message":"메일 API 요청 승인 (HTTP "+str(response.status_code)+"). 최종 배달은 메일함에서 확인하세요."}


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS followup_notice (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        talent_id INTEGER NOT NULL,
        last_contact TEXT NOT NULL,
        due_on TEXT NOT NULL,
        state TEXT NOT NULL,
        request_id TEXT NOT NULL UNIQUE,
        recorded_at TEXT NOT NULL,
        UNIQUE(talent_id,last_contact)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS followup_send (
        request_id TEXT PRIMARY KEY,
        talent_id INTEGER NOT NULL,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        state TEXT NOT NULL,
        attempted_at TEXT NOT NULL
    )""")
    db.commit()


def due_rows(db, on=None):
    on=on or today()
    rows=db.execute("""SELECT t.id,t.name,t.org,t.email,t.status,t.priority,
        MAX(ch.contact_at) AS last_contact
        FROM talent t LEFT JOIN contact_history ch ON ch.talent_id=t.id
        WHERE t.deleted_at IS NULL AND t.priority='핵심'
          AND t.status NOT IN ('보류','종료')
        GROUP BY t.id ORDER BY last_contact ASC""").fetchall()
    out=[]
    for row in rows:
        x=dict(row)
        if not x["last_contact"]:
            continue  # No real contact: cannot establish a six-month clock.
        try:
            last=date.fromisoformat(x["last_contact"])
        except ValueError:
            continue
        if last>on:
            continue
        due=add_months(last)
        if due<=on:
            x["due_on"]=due.isoformat()
            out.append(x)
    return out


def notices(db,on=None):
    init(db)
    sent={(r["talent_id"],r["last_contact"]):r["state"] for r in
          db.execute("SELECT talent_id,last_contact,state FROM followup_notice")}
    result=[]
    for item in due_rows(db,on):
        item["notice_state"]=sent.get((item["id"],item["last_contact"]),"알림대기")
        result.append(item)
    return result


def intranet_base(c):
    base=c.get("base_url","")
    u=urlsplit(base)
    if u.scheme!="http" or u.port!=8090 or not u.hostname or u.username or u.password or u.path not in ("","/") or u.query or u.fragment:
        raise ValueError("base_url은 사내 PC http://IPv4:8090 형식이어야 합니다.")
    import ipaddress
    try:
        ip=ipaddress.ip_address(u.hostname)
    except ValueError:
        raise ValueError("base_url에는 사내 PC IPv4 주소를 입력하세요.") from None
    if ip.version!=4 or not (ip.is_private or ip.is_loopback):
        raise ValueError("base_url은 사설 IPv4 주소여야 합니다.")
    return u.scheme+"://"+u.netloc


def notify_due(db, on=None):
    """Daily opt-in job: sends only administrator reminders, never candidate emails."""
    if os.getenv("FOLLOWUP_NOTIFY_ENABLED")!="1":
        return {"enabled":False,"due":len(notices(db,on)),"sent":0}
    c=config()
    base=intranet_base(c)
    init(db)
    delivered=0
    for item in due_rows(db,on):
        now=datetime.now(timezone.utc).isoformat()
        rid=str(uuid.uuid4())
        try:
            with db:
                db.execute("""INSERT INTO followup_notice
                    (talent_id,last_contact,due_on,state,request_id,recorded_at)
                    VALUES(?,?,?,?,?,?)""",
                    (item["id"],item["last_contact"],item["due_on"],"sending",rid,now))
        except sqlite3.IntegrityError:
            continue
        link=base+"/followups?talent_id="+str(item["id"])
        safe=lambda x:html.escape(str(x),quote=True)
        body=("<div style='font-family:Arial,sans-serif;line-height:1.7'>"
              "<h2>핵심 인재 6개월 근황 확인 알림</h2>"
              "<p><b>"+safe(item["name"])+"</b> ("+safe(item["org"])+")님의 최근 접촉일이 "
              +safe(item["last_contact"])+"로, 6개월이 경과했습니다.</p>"
              "<p>인재에게 메일이 자동 전송되지는 않습니다. 아래 버튼에서 내용을 검토·수정한 후 직접 발송하세요.</p>"
              "<p><a href='"+safe(link)+"' style='display:inline-block;background:#205595;color:white;"
              "padding:12px 22px;border-radius:8px;text-decoration:none'>메일 발송하기</a></p>"
              "<p>사내 네트워크 접속이 필요합니다.</p></div>")
        try:
            send_knox(c,c["notify_email"],"[Talent Pool] 핵심 인재 6개월 접촉 점검 - "+item["name"],body,rid)
            state="sent";delivered+=1
        except ValueError:
            state="uncertain"
        with db:
            db.execute("UPDATE followup_notice SET state=? WHERE request_id=?",(state,rid))
    return {"enabled":True,"due":len(due_rows(db,on)),"sent":delivered}


def draft(db,talent_id):
    from management import get_talent, contacts
    t=get_talent(db,talent_id)
    if not t or t["priority"]!="핵심" or t["status"] in ("보류","종료"):
        raise ValueError("활성 핵심 인재만 메일을 작성할 수 있습니다.")
    # The compose form may enter a one-time recipient even if no address
    # is saved on the talent profile. Drafting never modifies that profile.
    recipient=t.get("email") or ""
    if recipient:
        recipient=email_address(recipient)
    return {"talent_id":talent_id,"name":t["name"],"org":t["org"],
            "recipient":recipient,
            "subject":"안녕하세요, "+t["name"]+"님. 근황 인사드립니다.",
            "body":t["name"]+"님, 안녕하세요.\n\n오랜만에 인사드립니다. 그동안 잘 지내셨는지요?\n최근 연구 및 활동 근황이 궁금하여 연락드립니다. 편하실 때 소식 전해주시면 감사하겠습니다.\n\n감사합니다.",
            "request_id":str(uuid.uuid4())}


def send_candidate(db,talent_id,values):
    from management import get_talent, add_contact
    c=config()
    t=get_talent(db,talent_id)
    if not t or t["priority"]!="핵심" or t["status"] in ("보류","종료"):
        raise ValueError("핵심 관리 중인 인재만 발송할 수 있습니다.")
    # A recipient entered in the composer is limited to this single mail.
    # Keep the talent's stored address unchanged; audit the actual destination.
    recipient=email_address(values.get("recipient",""))
    subject=values.get("subject","")
    body=values.get("body","")
    rid=values.get("request_id","")
    if not isinstance(rid,str) or not re.fullmatch(r"[a-f0-9-]{36}",rid):
        raise ValueError("발송 화면을 다시 여세요.")
    if not isinstance(subject,str) or not 0<len(subject.strip())<=300 or not isinstance(body,str) or not 0<len(body.strip())<=15000:
        raise ValueError("메일 제목과 본문을 확인하세요.")
    now=datetime.now(timezone.utc).isoformat()
    init(db)
    # An attempt is persisted before the network call. All unknown outcomes
    # require manual checking; no automatic resend or duplicate contact logs.
    try:
        with db:
            db.execute("""INSERT INTO followup_send(request_id,talent_id,recipient,subject,state,attempted_at)
                VALUES(?,?,?,?,?,?)""",(rid,talent_id,recipient,subject.strip(),"sending",now))
    except sqlite3.IntegrityError:
        raise ValueError("이미 발송 시도한 요청입니다. 메일함을 확인하세요.") from None
    safe=html.escape(body).replace("\n","<br>")
    try:
        response=send_knox(c,recipient,subject,"<html><body><div style='font-family:Arial,sans-serif;line-height:1.7'>"+safe+"</div></body></html>",rid)
    except ValueError:
        with db:
            db.execute("UPDATE followup_send SET state='uncertain' WHERE request_id=?",(rid,))
        raise
    with db:
        db.execute("UPDATE followup_send SET state='accepted' WHERE request_id=?",(rid,))
        add_contact(db,talent_id,"이메일",subject.strip(),
            body,
            today().isoformat())
    return response
