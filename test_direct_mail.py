import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from management import database, edit_talent, get_talent
import direct_mail as m


class DirectMailTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict("os.environ",{
            "INTERNAL_DB_PATH":str(Path(self.temp.name)/"talent.db")
        })
        self.env.start();self.addCleanup(self.env.stop)
        db=database()
        db.execute("""INSERT INTO talent(identity_key,name,org,headline,domain,location,summary,
            why_fit,sources_json,created_at,updated_at,status,priority,email)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            "mail-1","김연구","서울대학교","박사후연구원","HBM thermal","","","","[]",
            "2026-01-01","2026-01-01","검토중","보통","original@university.edu"))
        db.execute("""INSERT INTO talent(identity_key,name,org,headline,domain,location,summary,
            why_fit,sources_json,created_at,updated_at,status,priority,email)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            "mail-2","박교수","KAIST","교수","AI","","","","[]",
            "2026-01-01","2026-01-01","보류","핵심","closed@university.edu"))
        db.commit();db.close()

    def test_search_by_person_org_and_research_field(self):
        db=database()
        for q in ("김연구","서울대","HBM","박사후연구원"):
            with self.subTest(query=q):
                rows=m.available(db,q)
                if q=="서울대":
                    # List query is literal; does not assume fuzzy institutional aliases.
                    continue
                self.assertEqual([x["id"] for x in rows],[1])
        self.assertEqual(m.available(db,""),[])
        self.assertEqual(m.available(db,"KAIST")[0]["id"],2)
        db.close()

    def test_draft_for_non_core_and_no_saved_email(self):
        db=database()
        p=m.draft(db,1)
        self.assertEqual(p["recipient"],"original@university.edu")
        self.assertEqual(p["name"],"김연구")
        self.assertNotEqual(p["request_id"],m.draft(db,1)["request_id"])
        db.execute("UPDATE talent SET email='' WHERE id=1")
        db.commit()
        self.assertEqual(m.draft(db,1)["recipient"],"")
        db.close()

    def test_send_uses_one_time_recipient_and_records_contact_once(self):
        db=database();d=m.draft(db,1)
        payload={"recipient":"one-time@research.edu","subject":"연구 협력 문의",
                 "body":"안녕하세요.","request_id":d["request_id"]}
        with patch.object(m,"config",return_value={"sender":"sender@samsung.com"}),patch.object(m,"send_knox",
                return_value={"status":"api_accepted","message":"API accepted"}) as transport:
            result=m.send(db,1,payload)
            self.assertEqual(result["status"],"api_accepted")
            self.assertEqual(transport.call_args.args[1],"one-time@research.edu")
            with self.assertRaisesRegex(ValueError,"이미 발송"):
                m.send(db,1,payload)
            self.assertEqual(transport.call_count,1)
        self.assertEqual(get_talent(db,1)["email"],"original@university.edu")
        self.assertEqual(get_talent(db,1)["status"],"접촉중")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM contact_history").fetchone()[0],1)
        log=db.execute("SELECT memo FROM contact_history").fetchone()[0]
        self.assertEqual(log,"안녕하세요.")
        row=db.execute("SELECT contact_at,channel,subject,memo FROM contact_history").fetchone()
        self.assertEqual((row["channel"],row["subject"],row["memo"]),("이메일","연구 협력 문의","안녕하세요."))
        db.close()

    def test_suspended_status_blocks_send_without_approval_code(self):
        db=database();d=m.draft(db,1)
        p={"recipient":"one-time@research.edu","subject":"문의","body":"안녕하세요.",
           "request_id":d["request_id"]}
        with self.assertRaisesRegex(ValueError,"보류"):
            m.draft(db,2)
        with patch.object(m,"send_knox") as transport:
            with self.assertRaisesRegex(ValueError,"보류"):
                m.send(db,2,p)
            transport.assert_not_called()
        db.close()

    def test_uncertain_response_never_creates_contact_and_no_retry(self):
        db=database();d=m.draft(db,1)
        p={"recipient":"candidate@research.edu","subject":"연락","body":"안부입니다.",
           "request_id":d["request_id"]}
        with patch.object(m,"config",return_value={"sender":"sender@samsung.com"}),patch.object(m,"send_knox",
                side_effect=ValueError("timeout")) as transport:
            with self.assertRaises(ValueError):m.send(db,1,p)
            with self.assertRaisesRegex(ValueError,"이미 발송"):m.send(db,1,p)
            self.assertEqual(transport.call_count,1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM contact_history").fetchone()[0],0)
        self.assertEqual(db.execute("SELECT state FROM direct_mail_send").fetchone()[0],"uncertain")
        db.close()

    def test_invalid_address_does_not_write_send_attempt(self):
        db=database();d=m.draft(db,1)
        with patch.object(m,"config") as c:
            with self.assertRaisesRegex(ValueError,"메일 주소"):
                m.send(db,1,{"recipient":"bad-address","subject":"제목","body":"내용",
                    "request_id":d["request_id"]})
            c.assert_not_called()
        db.close()


if __name__=="__main__":
    unittest.main()
