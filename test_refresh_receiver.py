import hashlib
import hmac
import json
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

from receiver import connect_db
from refresh_receiver import import_refresh_mail

SECRET="testing_monthly_secret_1234567890123"
SENDER="approved@example.org"

def make_refresh(batch="a"*32, tamper=False, proof="https://engineering.example.ac.kr/profile",old="가상대학"):
    obj={"schema_version":2,"kind":"talentpool_refresh","batch_id":batch,
         "sent_at":"2026-11-18T00:00:00Z",
         "reviews":[{"name":"가상 연구자","org":"가상대학","sources":["https://example.org"],
                     "identity_key":"fake","status":"changes_found","summary":"테스트",
                     "changes":[{"field":"org","old":old,"new":"신규대학",
                     "evidence_url":proof,
                     "evidence_excerpt":"공식 소속 설명","reason":"프로필 수정"}]}]}
    raw=json.dumps(obj,ensure_ascii=False,separators=(",",":"),sort_keys=True)
    msg=EmailMessage()
    msg["Subject"]="[TALENTPOOL-REFRESH] "+batch
    msg["From"]=SENDER
    msg["To"]="jobinfo@samsung.com"
    sign=hmac.new(SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
    msg["X-Talentpool-Signature"]="sha256="+("x"*64 if tamper else sign)
    msg.set_content("Monthly public-profile verification")
    msg.add_attachment(raw.encode(),maintype="application",subtype="json",filename="talentpool-refresh.json")
    return msg.as_bytes()

class RefreshTests(unittest.TestCase):
    def make_db(self,folder):
        db=connect_db(Path(folder)/"db.sqlite")
        db.execute("""INSERT INTO talent
            (identity_key,name,org,headline,domain,location,summary,why_fit,sources_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            ("id1","가상 연구자","가상대학","Professor","HBM","한국","요약","근거",
             '["https://engineering.example.ac.kr/profile"]',"2026-01-01","2026-01-01"))
        db.commit()
        return db

    def test_auto_apply_strong_source_and_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.make_db(folder)
            self.assertEqual(import_refresh_mail(db,make_refresh(),SECRET,SENDER),"imported")
            self.assertEqual(db.execute("SELECT org FROM talent").fetchone()[0],"신규대학")
            self.assertEqual(db.execute("SELECT result FROM applied_refresh").fetchone()[0],"applied")
            self.assertEqual(import_refresh_mail(db,make_refresh(),SECRET,SENDER),"duplicate")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM applied_refresh").fetchone()[0],1)
            db.close()

    def test_weak_source_cannot_override(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.make_db(folder)
            import_refresh_mail(db,make_refresh(proof="https://example.org/blog"),SECRET,SENDER)
            self.assertEqual(db.execute("SELECT org FROM talent").fetchone()[0],"가상대학")
            self.assertEqual(db.execute("SELECT result FROM applied_refresh").fetchone()[0],"skipped_weak_source")
            db.close()

    def test_stale_value_cannot_override(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.make_db(folder)
            import_refresh_mail(db,make_refresh(old="다른 소속"),SECRET,SENDER)
            self.assertEqual(db.execute("SELECT org FROM talent").fetchone()[0],"가상대학")
            self.assertEqual(db.execute("SELECT result FROM applied_refresh").fetchone()[0],"skipped_stale_or_conflicting")
            db.close()

    def test_manual_edit_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.make_db(folder)
            db.execute("ALTER TABLE talent ADD COLUMN edited_fields_json TEXT DEFAULT '[]'")
            db.execute('UPDATE talent SET edited_fields_json=?',('["org"]',))
            db.commit()
            import_refresh_mail(db,make_refresh(),SECRET,SENDER)
            self.assertEqual(db.execute("SELECT org FROM talent").fetchone()[0],"가상대학")
            self.assertEqual(db.execute("SELECT result FROM applied_refresh").fetchone()[0],"skipped_manually_curated")
            db.close()

    def test_unmatched_person_not_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"db.sqlite")
            import_refresh_mail(db,make_refresh(),SECRET,SENDER)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM talent").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT result FROM applied_refresh").fetchone()[0],"skipped_unmatched_identity")
            db.close()

    def test_invalid_signature_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"db.sqlite")
            with self.assertRaisesRegex(ValueError,"invalid HMAC signature"):
                import_refresh_mail(db,make_refresh(tamper=True),SECRET,SENDER)
            db.close()

if __name__=="__main__":unittest.main()
