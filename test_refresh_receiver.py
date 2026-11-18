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

def make_refresh(batch="a"*32, tamper=False):
    obj={"schema_version":2,"kind":"talentpool_refresh","batch_id":batch,
         "sent_at":"2026-11-18T00:00:00Z",
         "reviews":[{"name":"가상 연구자","org":"가상대학","sources":["https://example.org"],
                     "identity_key":"fake","status":"changes_found","summary":"테스트",
                     "changes":[{"field":"org","old":"가상대학","new":"신규대학",
                     "evidence_url":"https://example.org/new",
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
    def test_pending_review_not_direct_update(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"db.sqlite")
            self.assertEqual(import_refresh_mail(db,make_refresh(),SECRET,SENDER),"imported")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pending_refresh").fetchone()[0],1)
            self.assertEqual(import_refresh_mail(db,make_refresh(),SECRET,SENDER),"duplicate")
            # No talent row gets created or updated by review-only notifications.
            self.assertEqual(db.execute("SELECT COUNT(*) FROM talent").fetchone()[0],0)
            db.close()

    def test_invalid_signature_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"db.sqlite")
            with self.assertRaisesRegex(ValueError,"invalid HMAC signature"):
                import_refresh_mail(db,make_refresh(tamper=True),SECRET,SENDER)
            db.close()

if __name__=="__main__":unittest.main()
