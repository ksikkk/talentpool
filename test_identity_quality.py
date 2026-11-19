import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from email.message import EmailMessage
from receiver import connect_db, import_mail
from identity_quality import compare_profiles, evidence_quality
from duplicate_review import pending, resolve

SECRET="a_test_only_shared_secret_with_32_characters"
SENDER="source@example.org"

def mail_for(person,batch):
    obj={"schema_version":2,"kind":"talentpool_handoff","batch_id":batch,
         "talents":[person],"sent_at":"2026-11-19T00:00:00Z"}
    content=json.dumps(obj,ensure_ascii=False,separators=(",",":"),sort_keys=True)
    message=EmailMessage()
    message["From"]=SENDER
    message["To"]="jobinfo@samsung.com"
    message["Subject"]="[TALENTPOOL-IMPORT] "+batch
    message["X-Talentpool-Signature"]="sha256="+hmac.new(SECRET.encode(),content.encode(),hashlib.sha256).hexdigest()
    message.set_content("TALENTPOOL_JSON_V2\n"+content)
    message.add_attachment(content.encode(),maintype="application",subtype="json",filename="talentpool.json")
    return message.as_bytes()

def candidate(sources=None):
    return {"name":"가상 연구자","org":"가상 대학","headline":"Professor","domain":"HBM",
            "location":"Korea","summary":"Test profile","why_fit":"Demo only",
            "sources":sources or ["https://example.org/researcher-one"]}

class IdentityReliabilityTests(unittest.TestCase):
    def test_strong_orcid_and_name(self):
        a=candidate(["https://orcid.org/0000-0001-1234-567X"])
        b=candidate(["https://orcid.org/0000-0001-1234-567X"])
        self.assertEqual(compare_profiles(a,b)[0],"confirmed_id")
        b["name"]="다른 연구자"
        self.assertEqual(compare_profiles(a,b)[0],"review")

    def test_name_same_org_different_sources_requires_review(self):
        a=candidate(["https://example.org/profile-a"])
        b=candidate(["https://example.org/profile-b"])
        self.assertEqual(compare_profiles(a,b)[0],"review")

    def test_quality_is_heuristic_not_verified(self):
        grade=evidence_quality(candidate(["https://orcid.org/0000-0001-1234-567X","https://doi.org/10.1/abc"]))
        self.assertEqual(grade["grade"],"근거 풍부")
        self.assertIn("최종 검증",grade["note"])

    def test_mail_collision_goes_to_review_not_automerge(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect_db(Path(folder)/"pool.db")
            self.assertEqual(import_mail(db,mail_for(candidate(["https://example.org/prof-a"]),"a"*32),SECRET,SENDER),"imported")
            self.assertEqual(import_mail(db,mail_for(candidate(["https://example.org/prof-b"]),"b"*32),SECRET,SENDER),"imported")
            self.assertEqual(db.execute("SELECT count(*) FROM talent").fetchone()[0],1)
            records=pending(db)
            self.assertEqual(len(records),1)
            self.assertTrue(resolve(db,records[0]["id"],"distinct"))
            self.assertEqual(db.execute("SELECT count(*) FROM talent").fetchone()[0],2)
            db.close()

if __name__=="__main__": unittest.main()
