"""Internal-only POP3 receiver: does not export internal data or call OpenAI."""
import argparse, hashlib, hmac, json, os, poplib, re, sqlite3, ssl, sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlparse

def connect_db(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(p); db.row_factory=sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS talent(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      identity_key TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL, org TEXT NOT NULL,
      headline TEXT, domain TEXT, location TEXT, summary TEXT, why_fit TEXT,
      sources_json TEXT NOT NULL, status TEXT DEFAULT '검토대기',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS incoming_batch(
      batch_id TEXT PRIMARY KEY, message_id TEXT,
      received_at TEXT NOT NULL, talent_count INTEGER NOT NULL);
    """)
    db.commit()
    return db

def valid_url(value):
    try:
        u=urlparse(value)
        return u.scheme=="https" and bool(u.hostname) and "." in u.hostname and not(u.username or u.password)
    except ValueError: return False

def key_for(person):
    src=next((u for u in person["sources"] if any(d in (urlparse(u).hostname or "").lower() for d in ("orcid.org","scholar.google","linkedin.com"))),None)
    raw=src or (person["name"].strip().casefold()+"|"+person["org"].strip().casefold())
    return hashlib.sha256(raw.encode()).hexdigest()

def parse_mail(raw, secret, trusted_sender):
    if len(raw)>1024*1024: raise ValueError("oversize message")
    msg=BytesParser(policy=policy.default).parsebytes(raw)
    subject=msg.get("Subject","")
    if not subject.startswith("[TALENTPOOL-IMPORT] "): return None
    if msg.get("To","").lower().strip()!="jobinfo@samsung.com": raise ValueError("unexpected recipient")
    if parseaddr(msg.get("From",""))[1].lower()!=trusted_sender.lower(): raise ValueError("unexpected sender")
    part=msg.get_body(preferencelist=("plain",))
    if part is None or part.get_content_type()!="text/plain": raise ValueError("missing JSON text")
    body=part.get_content()
    prefix="TALENTPOOL_JSON_V2\n"
    if not body.startswith(prefix): raise ValueError("invalid marker")
    raw_json=body[len(prefix):].strip()
    expected="sha256="+hmac.new(secret.encode(),raw_json.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(msg.get("X-Talentpool-Signature",""),expected):
        raise ValueError("invalid HMAC signature")
    payload=json.loads(raw_json)
    if not isinstance(payload,dict) or payload.get("schema_version")!=2 or payload.get("kind")!="talentpool_handoff":
        raise ValueError("invalid schema")
    batch=payload.get("batch_id","")
    if not isinstance(batch,str) or re.fullmatch("[0-9a-f]{32}",batch) is None or not subject.endswith(batch):
        raise ValueError("invalid batch ID")
    people=payload.get("talents")
    if not isinstance(people,list) or not 1<=len(people)<=50: raise ValueError("invalid talent list")
    required={"name","org","headline","domain","location","summary","why_fit","sources"}
    for p in people:
        if not isinstance(p,dict) or set(p)!=required: raise ValueError("unexpected talent fields")
        if not all(isinstance(p[k],str) and len(p[k])<=3000 for k in required-{"sources"}):
            raise ValueError("invalid person field")
        if not p["name"].strip() or not p["org"].strip(): raise ValueError("missing name or organization")
        sources=p["sources"]
        if not isinstance(sources,list) or not 1<=len(sources)<=8 or not all(isinstance(u,str) and len(u)<1500 and valid_url(u) for u in sources):
            raise ValueError("invalid sources")
    return batch,people,msg.get("Message-ID","")

def import_mail(db,raw,secret,trusted_sender):
    parsed=parse_mail(raw,secret,trusted_sender)
    if parsed is None: return "ignored"
    batch,people,message_id=parsed
    now=datetime.now(timezone.utc).isoformat()
    with db:
        if db.execute("SELECT 1 FROM incoming_batch WHERE batch_id=?",(batch,)).fetchone():
            return "duplicate"
        for p in people:
            db.execute("""INSERT INTO talent(identity_key,name,org,headline,domain,location,summary,why_fit,sources_json,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(identity_key) DO UPDATE SET
              headline=excluded.headline, domain=excluded.domain, location=excluded.location,
              summary=excluded.summary, why_fit=excluded.why_fit, sources_json=excluded.sources_json,
              updated_at=excluded.updated_at""",
              (key_for(p),p["name"],p["org"],p["headline"],p["domain"],p["location"],p["summary"],
               p["why_fit"],json.dumps(p["sources"],ensure_ascii=False),now,now))
        db.execute("INSERT INTO incoming_batch(batch_id,message_id,received_at,talent_count) VALUES(?,?,?,?)",
                   (batch,message_id,now,len(people)))
    return "imported"

def poll_once():
    for name in ("POP3_USER","POP3_PASSWORD","HANDOFF_SECRET","TRUSTED_SENDER"):
        if not os.getenv(name): raise ValueError("Missing configuration: "+name)
    if len(os.environ["HANDOFF_SECRET"])<24: raise ValueError("HANDOFF_SECRET must have >=24 characters")
    db=connect_db(os.getenv("INTERNAL_DB_PATH","./internal_talents.db"))
    server=poplib.POP3_SSL(os.getenv("POP3_HOST","pop3.samsung.net"),port=int(os.getenv("POP3_PORT","995")),
                           timeout=25,context=ssl.create_default_context())
    result={"imported":0,"duplicate":0,"ignored":0,"rejected":0}
    try:
        server.user(os.environ["POP3_USER"]);server.pass_(os.environ["POP3_PASSWORD"])
        count=server.stat()[0]
        for n in range(max(1,count-int(os.getenv("POP3_SCAN_LIMIT","100"))+1),count+1):
            try:
                raw=b"\n".join(server.retr(n)[1])
                status=import_mail(db,raw,os.environ["HANDOFF_SECRET"],os.environ["TRUSTED_SENDER"])
                result[status]+=1
            except Exception as exc:
                result["rejected"]+=1
                print("Rejected message #"+str(n)+": "+type(exc).__name__,file=sys.stderr)
    finally:
        server.quit();db.close()
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--init-db",action="store_true")
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    if args.init_db:
        connect_db(os.getenv("INTERNAL_DB_PATH","./internal_talents.db")).close()
        print("Database initialized")
    elif args.once:
        print(json.dumps(poll_once(),ensure_ascii=False))
    else: parser.error("Specify --init-db or --once")
