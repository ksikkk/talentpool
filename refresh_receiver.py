"""Validate and store external PUBLIC profile-change suggestions; never export internal data.

These suggestions are review-only. Human approval is needed before modifying
candidate records, preventing overwrites due to mistaken identities.
"""
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, getaddresses

from receiver import valid_url
from identity_quality import profile_ids, url_key

ALLOWED_FIELDS={"org","headline","domain","email"}

def create_refresh_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS pending_refresh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        candidate_name TEXT NOT NULL,
        previous_org TEXT NOT NULL,
        field TEXT NOT NULL,
        old_value TEXT NOT NULL,
        proposed_value TEXT NOT NULL,
        evidence_url TEXT NOT NULL,
        evidence_excerpt TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT '검토대기',
        created_at TEXT NOT NULL,
        UNIQUE(batch_id,candidate_name,field,evidence_url)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS refresh_batch(
        batch_id TEXT PRIMARY KEY,
        received_at TEXT NOT NULL,
        item_count INTEGER NOT NULL
    )""")

def parse_refresh_mail(raw, secret, sender):
    if len(raw)>1024*1024:raise ValueError("oversize message")
    msg=BytesParser(policy=policy.default).parsebytes(raw)
    subject=str(msg.get("Subject",""))
    if not subject.startswith("[TALENTPOOL-REFRESH] "):
        return None
    recipients={a.lower() for _,a in getaddresses(msg.get_all("To",[])+msg.get_all("Cc",[]))}
    if "jobinfo@samsung.com" not in recipients:raise ValueError("unexpected recipient")
    if parseaddr(msg.get("From",""))[1].lower()!=sender.lower():raise ValueError("unexpected sender")
    parts=[p for p in msg.walk() if p.get_filename()=="talentpool-refresh.json" and p.get_content_type()=="application/json"]
    if len(parts)!=1:raise ValueError("missing signed refresh attachment")
    raw_bytes=parts[0].get_payload(decode=True)
    if not raw_bytes or len(raw_bytes)>512*1024:raise ValueError("invalid refresh attachment")
    obj=json.loads(raw_bytes.decode("utf-8"))
    canonical=json.dumps(obj,ensure_ascii=False,separators=(",",":"),sort_keys=True)
    signature=str(msg.get("X-Talentpool-Signature","")).strip()
    candidate="sha256="+hmac.new(secret.encode(),canonical.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,candidate):
        raise ValueError("invalid HMAC signature")
    batch=obj.get("batch_id","")
    if obj.get("schema_version")!=2 or obj.get("kind")!="talentpool_refresh" or not isinstance(batch,str) or not re.fullmatch("[0-9a-f]{32}",batch) or not subject.endswith(batch):
        raise ValueError("invalid refresh schema")
    reviews=obj.get("reviews")
    if not isinstance(reviews,list) or not 1<=len(reviews)<=50:
        raise ValueError("invalid refresh schema")
    out=[]
    for review in reviews:
        if not isinstance(review,dict):raise ValueError("invalid refresh schema")
        name=review.get("name")
        org=review.get("org")
        changes=review.get("changes")
        sources=review.get("sources",[])
        if not isinstance(sources,list) or len(sources)>20 or not all(isinstance(u,str) and valid_url(u) for u in sources):
            raise ValueError("invalid refresh schema")
        if not isinstance(name,str) or not name.strip() or len(name)>150 or not isinstance(org,str) or len(org)>200 or not isinstance(changes,list) or len(changes)>8:
            raise ValueError("invalid refresh schema")
        for item in changes:
            if not isinstance(item,dict) or item.get("field") not in ALLOWED_FIELDS:
                raise ValueError("invalid refresh schema")
            old,new,proof,excerpt,reason=(item.get(k) for k in ("old","new","evidence_url","evidence_excerpt","reason"))
            if not all(isinstance(x,str) for x in (old,new,proof,excerpt,reason)):
                raise ValueError("invalid refresh schema")
            if not new.strip() or not excerpt.strip() or not valid_url(proof) or len(proof)>1500 or len(new)>250 or len(old)>300 or len(excerpt)>250 or len(reason)>300:
                raise ValueError("invalid refresh schema")
            if item["field"]=="email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",new):
                raise ValueError("invalid refresh schema")
            out.append((batch,name,org,item["field"],old,new,proof,excerpt,reason,json.dumps(sources,ensure_ascii=False)))
    return batch,out

def import_refresh_mail(db,raw,secret,trusted_sender):
    """Apply signed, unambiguous public changes automatically; audit every decision.

    Never call an outside API. A signature proves the sender, NOT the truth of
    an AI-researched claim, so refuse ambiguous/unsupported/contradictory changes.
    """
    parsed=parse_refresh_mail(raw,secret,trusted_sender)
    if parsed is None:return "ignored"
    batch,items=parsed
    create_refresh_table(db)
    # Keep old schema as a migration path and preserve legacy records.
    cols={r["name"] for r in db.execute("PRAGMA table_info(talent)")}
    for key,definition in (
        ("last_public_refresh","TEXT NOT NULL DEFAULT ''"),
        ("deleted_at","TEXT"),
        ("edited_fields_json","TEXT NOT NULL DEFAULT '[]'"),
        ("email_source","TEXT NOT NULL DEFAULT ''"),
    ):
        if key not in cols:
            db.execute("ALTER TABLE talent ADD COLUMN "+key+" "+definition)
    db.execute("""CREATE TABLE IF NOT EXISTS applied_refresh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        talent_id INTEGER,
        candidate_name TEXT NOT NULL,
        field TEXT NOT NULL,
        old_value TEXT NOT NULL,
        new_value TEXT NOT NULL,
        evidence_url TEXT NOT NULL,
        result TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        UNIQUE(batch_id,candidate_name,field,evidence_url)
    )""")
    with db:
        if db.execute("SELECT 1 FROM refresh_batch WHERE batch_id=?",(batch,)).fetchone():
            return "duplicate"
        now=datetime.now(timezone.utc).isoformat()
        # Conflicting suggestions for the same person/field are not safe
        # to choose between without independent verification.
        from collections import Counter
        field_counts=Counter((name,org,field) for _,name,org,field,*_ in items)
        # Resolve each incoming person once from the ORIGINAL org/name.
        people={}
        for item in items:
            _,name,org,field,old,new,proof,excerpt,reason,source_json=item
            key=(name,org)
            if key not in people:
                rows=db.execute("""SELECT * FROM talent
                    WHERE name=? AND org=? AND deleted_at IS NULL""",(name,org)).fetchall()
                people[key]=rows[0] if len(rows)==1 else None
            row=people[key]
            outcome="skipped_unmatched_identity"
            if field_counts[(name,org,field)]>1:
                outcome="skipped_conflicting_suggestions"
            elif row is not None:
                incoming_urls=json.loads(source_json)
                stored_urls=json.loads(row["sources_json"])
                incoming_keys={url_key(u) for u in incoming_urls if url_key(u)}
                stored_keys={url_key(u) for u in stored_urls if url_key(u)}
                same_identity=bool((incoming_keys & stored_keys) or (profile_ids(incoming_urls)&profile_ids(stored_urls)))
                # Protect manual edits, stale reports, and unclear evidence.
                edited=set(json.loads(row["edited_fields_json"] or "[]")) if "edited_fields_json" in row.keys() else set()
                from identity_quality import kinds
                quality=kinds(proof)
                value=row[field] or ""
                if not same_identity:
                    outcome="skipped_identity_evidence"
                elif field in edited:
                    outcome="skipped_manually_curated"
                elif value.strip().casefold()!=old.strip().casefold():
                    outcome="skipped_stale_or_conflicting"
                elif quality not in ("교육·연구기관 도메인","공공기관 도메인","연구자 식별정보"):
                    outcome="skipped_weak_source"
                elif new.strip().casefold()==value.strip().casefold():
                    outcome="unchanged"
                else:
                    updates={field:new,"updated_at":now,"last_public_refresh":now}
                    if field=="email":updates["email_source"]=proof
                    assignments=", ".join(k+"=?" for k in updates)
                    db.execute("UPDATE talent SET "+assignments+" WHERE id=?",
                               (*updates.values(),row["id"]))
                    outcome="applied"
                    # Future changes in same batch compare to their own original values.
            db.execute("""INSERT OR IGNORE INTO applied_refresh
                (batch_id,talent_id,candidate_name,field,old_value,new_value,evidence_url,result,applied_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (batch,row["id"] if row else None,name,field,old,new,proof,outcome,now))
        db.execute("INSERT INTO refresh_batch(batch_id,received_at,item_count) VALUES(?,?,?)",(batch,now,len(items)))
    return "imported"
