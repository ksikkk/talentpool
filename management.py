"""Local talent management database helpers. No network access."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from receiver import connect_db
from identity_quality import evidence_quality

STATUSES = ("검토대기", "검토중", "관심", "접촉예정", "접촉중", "보류", "종료")
PRIORITIES = ("미분류", "핵심", "높음", "보통", "낮음")
CONTACT_TYPES = ("이메일", "전화", "미팅", "기타")

def now():
    return datetime.now(timezone.utc).isoformat()

def database():
    db = connect_db(os.getenv("INTERNAL_DB_PATH", "./internal_talents.db"))
    # Additive migration: preserve all existing talent rows and email import history.
    columns = {r["name"] for r in db.execute("PRAGMA table_info(talent)")}
    for key, definition in (
        ("priority", "TEXT NOT NULL DEFAULT '미분류'"),
        ("email", "TEXT NOT NULL DEFAULT ''"),
        ("email_source", "TEXT NOT NULL DEFAULT ''"),
        ("classification", "TEXT NOT NULL DEFAULT ''"),
        ("deleted_at", "TEXT"),
        ("requested_field", "TEXT NOT NULL DEFAULT ''"),
        ("edited_fields_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("owner", "TEXT NOT NULL DEFAULT ''"),
        ("internal_notes", "TEXT NOT NULL DEFAULT ''"),
        ("next_action", "TEXT NOT NULL DEFAULT ''"),
        ("next_action_date", "TEXT NOT NULL DEFAULT ''"),
    ):
        if key not in columns:
            db.execute("ALTER TABLE talent ADD COLUMN " + key + " " + definition)
    db.execute("""CREATE TABLE IF NOT EXISTS contact_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        talent_id INTEGER NOT NULL REFERENCES talent(id),
        contact_at TEXT NOT NULL,
        channel TEXT NOT NULL,
        subject TEXT NOT NULL,
        memo TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS ix_contact_talent ON contact_history(talent_id,contact_at DESC)")
    db.execute("""CREATE TABLE IF NOT EXISTS talent_field(
        talent_id INTEGER NOT NULL, field TEXT NOT NULL,
        PRIMARY KEY(talent_id,field)
    )""")
    db.execute("""INSERT OR IGNORE INTO talent_field(talent_id,field)
        SELECT id,requested_field FROM talent WHERE requested_field!=''""")
    db.commit()
    return db

def talent_as_dict(row):
    item = dict(row)
    item["sources"] = json.loads(item.pop("sources_json"))
    item["source_quality"] = evidence_quality(item)
    item["requested_fields"] = json.loads(item.pop("field_groups_json") or "[]")
    item["has_contact"] = bool(item.get("contact_count", 0))
    return item

def list_talents(db, q="", status="", priority="", domain="", limit=200):
    where, params = [], []
    where.append("talent.deleted_at IS NULL")
    if q:
        where.append("(name LIKE ? OR org LIKE ? OR headline LIKE ? OR domain LIKE ?)")
        params += ["%" + q[:100] + "%"] * 4
    if status:
        where.append("status=?"); params.append(status)
    if priority:
        where.append("priority=?"); params.append(priority)
    if domain:
        where.append("domain LIKE ?"); params.append("%" + domain[:100] + "%")
    statement = """SELECT talent.*, (SELECT COUNT(*) FROM contact_history ch WHERE ch.talent_id=talent.id) AS contact_count, (SELECT json_group_array(field) FROM talent_field tf WHERE tf.talent_id=talent.id) AS field_groups_json FROM talent"""
    if where: statement += " WHERE " + " AND ".join(where)
    statement += " ORDER BY updated_at DESC,id DESC LIMIT ?"
    params.append(min(max(int(limit),1),500))
    return [talent_as_dict(r) for r in db.execute(statement, params).fetchall()]

def get_talent(db, talent_id):
    row = db.execute("""SELECT talent.*, (SELECT COUNT(*) FROM contact_history ch WHERE ch.talent_id=talent.id) AS contact_count, (SELECT json_group_array(field) FROM talent_field tf WHERE tf.talent_id=talent.id) AS field_groups_json FROM talent WHERE talent.id=? AND talent.deleted_at IS NULL""", (talent_id,)).fetchone()
    return talent_as_dict(row) if row else None

def edit_talent(db, talent_id, updates):
    import re
    from receiver import valid_url
    allowed = {"status", "priority", "internal_notes", "name", "org", "headline",
               "domain", "summary", "why_fit", "email", "sources", "requested_field", "classification"}
    if not updates or any(k not in allowed for k in updates):
        raise ValueError("invalid update fields")
    for k,v in updates.items():
        if k == "sources":
            if not isinstance(v,list) or len(v)>20 or not all(isinstance(u,str) and len(u)<=1500 and valid_url(u) for u in v):
                raise ValueError("invalid sources")
        elif not isinstance(v,str) or len(v) > (4000 if k in {"internal_notes","summary","why_fit"} else 300):
            raise ValueError("invalid field value")
        elif k=="status" and v not in STATUSES: raise ValueError("invalid status")
        elif k=="priority" and v not in PRIORITIES: raise ValueError("invalid priority")
        elif k in {"name","org"} and not v.strip(): raise ValueError("name and organization required")
        elif k=="email" and v and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",v):
            raise ValueError("invalid email")
    existing=get_talent(db,talent_id)
    if not existing: return None
    converted={("sources_json" if k=="sources" else k):
        (json.dumps(v,ensure_ascii=False) if k=="sources" else v) for k,v in updates.items()}
    curated={"name","org","headline","domain","summary","why_fit","sources"}
    edited=set(json.loads(existing.get("edited_fields_json") or "[]"))
    edited.update(curated.intersection(updates))
    converted["edited_fields_json"]=json.dumps(sorted(edited),ensure_ascii=False)
    fields=", ".join(k+"=?" for k in converted)
    with db:
        db.execute("UPDATE talent SET "+fields+" WHERE id=?", [*converted.values(),talent_id])
        if "requested_field" in updates and updates["requested_field"].strip():
            db.execute("INSERT OR IGNORE INTO talent_field(talent_id,field) VALUES(?,?)",
                       (talent_id,updates["requested_field"].strip()))
    return get_talent(db,talent_id)

def add_contact(db,talent_id,channel,subject,memo,contact_at):
    from datetime import date
    if channel not in CONTACT_TYPES or not isinstance(subject,str) or not subject.strip() or len(subject)>200:
        raise ValueError("invalid contact")
    if not isinstance(memo,str) or len(memo)>4000: raise ValueError("invalid contact")
    try:
        if date.fromisoformat(contact_at).isoformat()!=contact_at: raise ValueError()
    except (ValueError,TypeError): raise ValueError("invalid contact date")
    if not get_talent(db,talent_id): return None
    with db:
        cur=db.execute(
            "INSERT INTO contact_history(talent_id,contact_at,channel,subject,memo,created_at) VALUES(?,?,?,?,?,?)",
            (talent_id,contact_at,channel,subject.strip(),memo,now()))
    return cur.lastrowid

def contacts(db,talent_id):
    return [dict(r) for r in db.execute(
        "SELECT * FROM contact_history WHERE talent_id=? ORDER BY contact_at DESC,id DESC LIMIT 300",(talent_id,))]

def delete_talent(db, talent_id):
    """Recoverable soft deletion, retaining history for authorized recovery."""
    if not get_talent(db,talent_id):
        return False
    with db:
        db.execute("UPDATE talent SET deleted_at=? WHERE id=? AND deleted_at IS NULL",(now(),talent_id))
    return True
