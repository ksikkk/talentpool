import hashlib
import hmac
import json
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from receiver import connect_db, import_mail

SECRET = "internal_test_secret_123456789012"
SENDER = "approved@example.com"

def sample_mail(batch="a" * 32, valid=True):
    p = {
        "schema_version": 2,
        "kind": "talentpool_handoff",
        "batch_id": batch,
        "sent_at": "2026-11-18T00:00:00Z",
        "talents": [{
            "name": "테스트 인재", "org": "예시 연구소",
            "headline": "책임연구원", "domain": "HBM",
            "location": "한국", "summary": "공개 논문",
            "why_fit": "공식 출처", "sources": ["https://example.org/profile"]
        }]
    }
    raw = json.dumps(p, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = "jobinfo@samsung.com"
    msg["Subject"] = "[TALENTPOOL-IMPORT] " + batch
    msg["X-Talentpool-Signature"] = ("sha256=" + hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()) if valid else "sha256=invalid"
    msg.set_content("TALENTPOOL_JSON_V2\n" + raw)
    return msg.as_bytes()

class ReceiverTests(unittest.TestCase):
    def test_import_once(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            self.assertEqual(import_mail(db,sample_mail(),SECRET,SENDER),"imported")
            self.assertEqual(import_mail(db,sample_mail(),SECRET,SENDER),"duplicate")
            self.assertEqual(db.execute("SELECT count(*) FROM talent").fetchone()[0],1)
            db.close()

    def test_invalid_signature_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            with self.assertRaises(ValueError):
                import_mail(db,sample_mail(valid=False),SECRET,SENDER)
            self.assertEqual(db.execute("SELECT count(*) FROM talent").fetchone()[0],0)
            db.close()

    def test_recipient_display_name_accepted(self):
        raw=sample_mail()
        raw=raw.replace(b"To: jobinfo@samsung.com",b"To: Job Info <jobinfo@samsung.com>")
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            self.assertEqual(import_mail(db,raw,SECRET,SENDER),"imported")
            db.close()

    def test_invalid_sender_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            with self.assertRaises(ValueError):
                import_mail(db,sample_mail(),SECRET,"other@example.com")
            db.close()

if __name__=="__main__": unittest.main()
