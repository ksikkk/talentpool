"""Manual resolution of signed incoming profiles flagged as possible duplicates."""
import hashlib
import json
from datetime import datetime,timezone

from receiver import key_for


def pending(db):
    rows=db.execute("""SELECT d.id,d.name,d.org,d.candidate_json,d.matched_talent_id,
       d.reason,d.created_at,t.name AS existing_name,t.org AS existing_org
       FROM duplicate_review d JOIN talent t ON t.id=d.matched_talent_id
       WHERE d.resolution='검토대기' ORDER BY d.id DESC LIMIT 200""").fetchall()
    return [{**dict(r),"candidate":json.loads(r["candidate_json"])} for r in rows]


def resolve(db,review_id,decision):
    if decision not in ("same","distinct"):
        raise ValueError("invalid decision")
    row=db.execute("SELECT * FROM duplicate_review WHERE id=? AND resolution='검토대기'",(review_id,)).fetchone()
    if not row:return False
    person=json.loads(row["candidate_json"])
    now=datetime.now(timezone.utc).isoformat()
    with db:
        if decision=="distinct":
            identity=hashlib.sha256((key_for(person)+"|human-distinct|"+str(review_id)).encode()).hexdigest()
            db.execute("""INSERT INTO talent(
              identity_key,name,org,headline,domain,location,summary,why_fit,sources_json,
              requested_field,email,email_source,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (identity,person["name"],person["org"],person["headline"],person["domain"],person["location"],
               person["summary"],person["why_fit"],json.dumps(person["sources"],ensure_ascii=False),
               person.get("requested_field",""),person.get("email",""),person.get("email_source",""),now,now))
            tid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            for group in dict.fromkeys([*person.get("requested_fields",[]),person.get("requested_field","")]):
                if group:db.execute("INSERT OR IGNORE INTO talent_field(talent_id,field) VALUES(?,?)",(tid,group))
        db.execute("UPDATE duplicate_review SET resolution=? WHERE id=?",(decision,review_id))
    return True
