import hashlib
import hmac
import json
import tempfile
import unittest
from email.message import EmailMessage
from email import policy
from email.parser import BytesParser
from pathlib import Path
from receiver import connect_db, import_mail

SECRET = "internal_test_secret_123456789012"
SENDER = "approved@example.com"

def sample_mail(batch="a" * 32, valid=True, with_discovery=False, field="HBM"):
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
    if with_discovery:
        p["talents"][0].update({
            "requested_field":field,
            "email":"researcher@example.org",
            "email_source":"https://example.org/profile"
        })
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

    def test_reformatted_json_whitespace(self):
        raw=sample_mail()
        msg=BytesParser(policy=policy.default).parsebytes(raw)
        old=msg.get_body(preferencelist=("plain",)).get_content()
        obj=json.loads(old.split("\n",1)[1])
        msg.set_content("TALENTPOOL_JSON_V2\n"+json.dumps(obj,ensure_ascii=False,indent=2))
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            self.assertEqual(import_mail(db,msg.as_bytes(),SECRET,SENDER),"imported")
            db.close()

    def test_signed_json_attachment(self):
        from email import policy
        from email.parser import BytesParser
        msg=BytesParser(policy=policy.default).parsebytes(sample_mail())
        body=msg.get_body(preferencelist=("plain",)).get_content()
        signed_json=body.split("\n",1)[1].strip()
        msg.add_attachment(signed_json.encode("utf-8"),maintype="application",subtype="json",filename="talentpool.json")
        # Deliberately alter the legacy body: attachment must remain signed.
        msg.get_body(preferencelist=("plain",)).set_content("Corporate banner replaced body")
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            self.assertEqual(import_mail(db,msg.as_bytes(),SECRET,SENDER),"imported")
            db.close()

    def test_discovery_fields_and_email_import(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            self.assertEqual(import_mail(db,sample_mail(with_discovery=True),SECRET,SENDER),"imported")
            row=db.execute("SELECT id,requested_field,email,email_source FROM talent").fetchone()
            self.assertEqual(row["requested_field"],"HBM")
            self.assertEqual(row["email"],"researcher@example.org")
            self.assertEqual(row["email_source"],"https://example.org/profile")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM talent_field").fetchone()[0],1)
            # A second valid request for the same person is an additional grouping, not a duplicate person.
            self.assertEqual(import_mail(db,sample_mail(batch="b"*32,with_discovery=True,field="첨단 패키징"),SECRET,SENDER),"imported")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM talent").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM talent_field").fetchone()[0],2)
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
