"""Local talent management database helpers. No network access."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from receiver import connect_db

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
    db.commit()
    return db

def talent_as_dict(row):
    item = dict(row)
    item["sources"] = json.loads(item.pop("sources_json"))
    return item

def list_talents(db, q="", status="", priority="", domain="", limit=200):
    where, params = [], []
    if q:
        where.append("(name LIKE ? OR org LIKE ? OR headline LIKE ? OR domain LIKE ?)")
        params += ["%" + q[:100] + "%"] * 4
    if status:
        where.append("status=?"); params.append(status)
    if priority:
        where.append("priority=?"); params.append(priority)
    if domain:
        where.append("domain LIKE ?"); params.append("%" + domain[:100] + "%")
    statement = "SELECT * FROM talent"
    if where: statement += " WHERE " + " AND ".join(where)
    statement += " ORDER BY updated_at DESC,id DESC LIMIT ?"
    params.append(min(max(int(limit),1),500))
    return [talent_as_dict(r) for r in db.execute(statement, params).fetchall()]

def get_talent(db, talent_id):
    row = db.execute("SELECT * FROM talent WHERE id=?", (talent_id,)).fetchone()
    return talent_as_dict(row) if row else None

def edit_talent(db, talent_id, updates):
    allowed = {"status", "priority", "owner", "internal_notes", "next_action", "next_action_date"}
    if not updates or any(k not in allowed for k in updates):
        raise ValueError("invalid update fields")
    for k,v in updates.items():
        if not isinstance(v,str) or len(v) > (4000 if k=="internal_notes" else 200):
            raise ValueError("invalid field value")
        if k=="status" and v not in STATUSES: raise ValueError("invalid status")
        if k=="priority" and v not in PRIORITIES: raise ValueError("invalid priority")
        if k=="next_action_date" and v:
            from datetime import date
            try:
                if date.fromisoformat(v).isoformat()!=v: raise ValueError()
            except ValueError: raise ValueError("invalid date")
    if not get_talent(db,talent_id): return None
    fields = ", ".join(k+"=?" for k in updates)
    with db:
        db.execute("UPDATE talent SET "+fields+" WHERE id=?", [*updates.values(),talent_id])
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
