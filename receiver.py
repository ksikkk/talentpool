"""Internal-only POP3 receiver: does not export internal data or call OpenAI."""
import argparse, hashlib, hmac, json, os, poplib, re, sqlite3, ssl, sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, getaddresses
from pathlib import Path
from urllib.parse import urlparse
from identity_quality import compare_profiles, profile_ids

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
    # Additive migration applies even if mail receiver runs before the web viewer.
    existing={r["name"] for r in db.execute("PRAGMA table_info(talent)")}
    for key,kind in [
        ("requested_field","TEXT NOT NULL DEFAULT ''"),
        ("email","TEXT NOT NULL DEFAULT ''"),
        ("email_source","TEXT NOT NULL DEFAULT ''"),
    ]:
        if key not in existing: db.execute("ALTER TABLE talent ADD COLUMN "+key+" "+kind)
    db.execute("""CREATE TABLE IF NOT EXISTS talent_field(
        talent_id INTEGER NOT NULL, field TEXT NOT NULL,
        PRIMARY KEY(talent_id,field)
    )""")
    db.execute("""INSERT OR IGNORE INTO talent_field(talent_id,field)
        SELECT id,requested_field FROM talent WHERE requested_field!=''""")
    db.execute("""CREATE TABLE IF NOT EXISTS duplicate_review (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        name TEXT NOT NULL,
        org TEXT NOT NULL,
        candidate_json TEXT NOT NULL,
        matched_talent_id INTEGER NOT NULL,
        reason TEXT NOT NULL,
        resolution TEXT NOT NULL DEFAULT '검토대기',
        created_at TEXT NOT NULL,
        UNIQUE(batch_id,name,org,matched_talent_id)
    )""")
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
    # Mail gateways may add a display name or additional recipients.
    recipients={addr.lower() for _,addr in getaddresses(msg.get_all("To",[]) + msg.get_all("Cc",[]))}
    if "jobinfo@samsung.com" not in recipients: raise ValueError("unexpected recipient")
    if parseaddr(msg.get("From",""))[1].lower()!=trusted_sender.lower(): raise ValueError("unexpected sender")
    # Prefer the signed JSON attachment: mail gateways often modify plain-text
    # bodies (security banners, line wrapping), but preserve attachments.
    attachments=[p for p in msg.walk() if p.get_filename()=="talentpool.json" and p.get_content_type()=="application/json"]
    if len(attachments)>1: raise ValueError("multiple JSON attachments")
    if attachments:
        raw_bytes=attachments[0].get_payload(decode=True)
        if not raw_bytes or len(raw_bytes)>512*1024: raise ValueError("invalid JSON attachment")
        raw_json=raw_bytes.decode("utf-8")
    else:
        part=msg.get_body(preferencelist=("plain",))
        if part is None or part.get_content_type()!="text/plain": raise ValueError("missing JSON text")
        body=part.get_content()
        prefix="TALENTPOOL_JSON_V2\n"
        if not body.startswith(prefix): raise ValueError("invalid marker")
        raw_json=body[len(prefix):].strip()
    # Require strict JSON; never deserialize arbitrary data or accept unsigned content.
    payload=json.loads(raw_json)
    signature=msg.get("X-Talentpool-Signature","").strip()
    def signed(value):
        candidate="sha256="+hmac.new(secret.encode(),value.encode("utf-8"),hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature,candidate)
    # A mail gateway may reformat whitespace in a JSON body. The sender uses
    # json.dumps(..., ensure_ascii=False, separators=(',', ':'), sort_keys=True).
    # Accept either exact transport bytes or the *same JSON object* in that
    # canonical sender representation. Do not disable HMAC checking.
    canonical=json.dumps(payload,ensure_ascii=False,separators=(",",":"),sort_keys=True)
    if not (signed(raw_json) or signed(canonical)):
        raise ValueError("invalid HMAC signature")
    if not isinstance(payload,dict) or payload.get("schema_version")!=2 or payload.get("kind")!="talentpool_handoff":
        raise ValueError("invalid schema")
    batch=payload.get("batch_id","")
    if not isinstance(batch,str) or re.fullmatch("[0-9a-f]{32}",batch) is None or not subject.endswith(batch):
        raise ValueError("invalid batch ID")
    people=payload.get("talents")
    if not isinstance(people,list) or not 1<=len(people)<=50: raise ValueError("invalid talent list")
    required={"name","org","headline","domain","location","summary","why_fit","sources"}
    optional={"requested_field","requested_fields","email","email_source"}
    for p in people:
        if not isinstance(p,dict) or not required.issubset(p) or not set(p).issubset(required|optional):
            raise ValueError("unexpected talent fields")
        if not all(isinstance(p[k],str) and len(p[k])<=3000 for k in required-{"sources"}):
            raise ValueError("invalid person field")
        if not p["name"].strip() or not p["org"].strip(): raise ValueError("missing name or organization")
        sources=p["sources"]
        if not isinstance(sources,list) or not 1<=len(sources)<=8 or not all(isinstance(u,str) and len(u)<1500 and valid_url(u) for u in sources):
            raise ValueError("invalid sources")
        if not isinstance(p.get("requested_field",""),str) or len(p.get("requested_field",""))>130:
            raise ValueError("invalid requested field")
        groups=p.get("requested_fields",[])
        if not isinstance(groups,list) or len(groups)>20 or any(not isinstance(x,str) or not x.strip() or len(x)>130 for x in groups):
            raise ValueError("invalid requested field")
        mail=p.get("email","")
        proof=p.get("email_source","")
        if not isinstance(mail,str) or not isinstance(proof,str) or len(mail)>254 or len(proof)>1500:
            raise ValueError("invalid professional email")
        if bool(mail)!=bool(proof) or (mail and (not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",mail) or not valid_url(proof) or proof not in sources)):
            raise ValueError("invalid professional email")
    return batch,people,msg.get("Message-ID","")

def import_mail(db,raw,secret,trusted_sender):
    parsed=parse_mail(raw,secret,trusted_sender)
    if parsed is None: return "ignored"
    batch,people,message_id=parsed
    now=datetime.now(timezone.utc).isoformat()
    with db:
        if db.execute("SELECT 1 FROM incoming_batch WHERE batch_id=?",(batch,)).fetchone():
            return "duplicate"
        columns={row["name"] for row in db.execute("PRAGMA table_info(talent)")}
        curated_available="edited_fields_json" in columns
        for p in people:
            identity=key_for(p)
            # Never silently merge names sharing an institutional affiliation.
            # If a strong profile ID is reused with a different name, quarantine.
            matched=db.execute("SELECT * FROM talent WHERE identity_key=?",(identity,)).fetchone()
            existing=db.execute("SELECT * FROM talent WHERE deleted_at IS NULL AND name=? AND org=? LIMIT 15",
                                (p["name"],p["org"])).fetchall() if "deleted_at" in columns else db.execute(
                                "SELECT * FROM talent WHERE name=? AND org=? LIMIT 15",(p["name"],p["org"])).fetchall()
            possible=[]
            for old in existing + ([matched] if matched and all(old["id"]!=matched["id"] for old in existing) else []):
                old_person={**dict(old),"sources":json.loads(old["sources_json"])}
                tier,reason=compare_profiles(p,old_person)
                if old["identity_key"]==identity and tier in ("confirmed_id","exact_record"):
                    continue
                if old["identity_key"]!=identity and tier=="distinct":
                    continue
                possible.append((old["id"],reason))
            if possible:
                for old_id,reason in possible:
                    db.execute("""INSERT OR IGNORE INTO duplicate_review(
                      batch_id,name,org,candidate_json,matched_talent_id,reason,created_at)
                      VALUES(?,?,?,?,?,?,?)""",
                      (batch,p["name"],p["org"],json.dumps(p,ensure_ascii=False),old_id,reason,now))
                continue
            db.execute("""INSERT OR IGNORE INTO talent(identity_key,name,org,headline,domain,location,summary,why_fit,sources_json,created_at,updated_at,requested_field,email,email_source)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (identity,p["name"],p["org"],p["headline"],p["domain"],p["location"],p["summary"],
               p["why_fit"],json.dumps(p["sources"],ensure_ascii=False),now,now,
               p.get("requested_field",""),p.get("email",""),p.get("email_source","")))
            row=db.execute("SELECT * FROM talent WHERE identity_key=?",(identity,)).fetchone()
            protected=set(json.loads(row["edited_fields_json"] or "[]")) if curated_available else set()
            new_values={"headline":p["headline"],"domain":p["domain"],"location":p["location"],
                        "summary":p["summary"],"why_fit":p["why_fit"],
                        "sources_json":json.dumps(p["sources"],ensure_ascii=False)}
            new_values={k:v for k,v in new_values.items() if
                        ("sources" if k=="sources_json" else k) not in protected}
            if p.get("email") and not row["email"] and "email" not in protected:
                new_values["email"]=p["email"]
                new_values["email_source"]=p.get("email_source","")
            if p.get("requested_field") and not row["requested_field"]:
                new_values["requested_field"]=p["requested_field"]
            fields=list(dict.fromkeys([*p.get("requested_fields",[]),p.get("requested_field","")]))
            for field in fields:
                if field.strip():
                    db.execute("INSERT OR IGNORE INTO talent_field(talent_id,field) VALUES(?,?)",
                               (row["id"],field.strip()))
            new_values["updated_at"]=now
            assignments=", ".join(k+"=?" for k in new_values)
            db.execute("UPDATE talent SET "+assignments+" WHERE identity_key=?",
                       [*new_values.values(),identity])
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
                if b"[TALENTPOOL-REFRESH]" in raw[:8192]:
                    from refresh_receiver import import_refresh_mail
                    status=import_refresh_mail(db,raw,os.environ["HANDOFF_SECRET"],os.environ["TRUSTED_SENDER"])
                else:
                    status=import_mail(db,raw,os.environ["HANDOFF_SECRET"],os.environ["TRUSTED_SENDER"])
                result[status]+=1
            except Exception as exc:
                result["rejected"]+=1
                # Only fixed validation reason codes are logged: never headers, JSON, passwords, or candidate data.
                allowed={"oversize message","unexpected recipient","unexpected sender","missing JSON text",
                         "invalid marker","invalid JSON attachment","multiple JSON attachments","invalid HMAC signature","invalid schema","invalid batch ID",
                         "invalid talent list","unexpected talent fields","invalid person field",
                         "missing name or organization","invalid sources","invalid requested field","invalid professional email"}
                reason=str(exc) if isinstance(exc,ValueError) and str(exc) in allowed else type(exc).__name__
                print(f"Rejected message #{n}: {reason}",file=sys.stderr)
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
