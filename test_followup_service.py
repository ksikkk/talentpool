import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from management import database, add_contact, edit_talent, get_talent
from receiver import connect_db
import followup_service as f


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.patcher=patch.dict("os.environ",{"INTERNAL_DB_PATH":str(Path(self.folder.name)/"db.sqlite"),
                                             "FOLLOWUP_NOTIFY_ENABLED":"0",
                                             "FOLLOWUP_APPROVAL_CODE":"testing-long-secret"})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        db=database()
        db.execute("""INSERT INTO talent(identity_key,name,org,headline,domain,location,summary,why_fit,
          sources_json,created_at,updated_at,status,priority,email)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          ("id-test","테스트 연구원","예시 대학","","HBM","","","",
           '["https://example.org/person"]',"2025-01-01","2025-01-01",
           "접촉중","핵심","researcher@example.org"))
        db.commit()
        db.close()

    def test_month_end_and_leap_day(self):
        self.assertEqual(f.add_months(date(2026,8,31)),date(2027,2,28))
        self.assertEqual(f.add_months(date(2023,8,31)),date(2024,2,29))

    def test_only_six_month_core_with_contact_history(self):
        db=database()
        self.assertEqual(f.due_rows(db,date(2026,11,19)),[])
        add_contact(db,1,"이메일","과거 연락","","2026-05-19")
        self.assertEqual(len(f.due_rows(db,date(2026,11,18))),0)
        self.assertEqual(len(f.due_rows(db,date(2026,11,19))),1)
        edit_talent(db,1,{"priority":"보통"})
        self.assertEqual(f.due_rows(db,date(2026,11,19)),[])
        edit_talent(db,1,{"priority":"핵심","status":"보류"})
        self.assertEqual(f.due_rows(db,date(2026,11,19)),[])
        db.close()

    def test_new_contact_restarts_six_month_clock(self):
        db=database()
        add_contact(db,1,"이메일","6개월 전","","2026-05-19")
        self.assertEqual(len(f.due_rows(db,date(2026,11,19))),1)
        add_contact(db,1,"전화","추가 연락","","2026-11-19")
        self.assertEqual(f.due_rows(db,date(2026,11,19)),[])
        self.assertEqual(f.due_rows(db,date(2027,5,18)),[])
        self.assertEqual(len(f.due_rows(db,date(2027,5,19))),1)
        db.close()

    def test_notify_does_not_send_without_opt_in(self):
        db=database()
        add_contact(db,1,"이메일","과거 연락","","2026-05-19")
        with patch.object(f,"send_knox") as send:
            result=f.notify_due(db,date(2026,11,19))
            send.assert_not_called()
        self.assertFalse(result["enabled"])
        db.close()

    def test_notification_only_once_per_last_contact(self):
        db=database()
        add_contact(db,1,"이메일","과거 연락","","2026-05-19")
        c={"sender":"admin@samsung.com","notify_email":"manager@samsung.com",
           "base_url":"http://192.168.1.30:8090"}
        with patch.dict("os.environ",{"FOLLOWUP_NOTIFY_ENABLED":"1"}), patch.object(f,"config",return_value=c), patch.object(f,"send_knox",return_value={"status":"api_accepted"}) as send:
            self.assertEqual(f.notify_due(db,date(2026,11,19))["sent"],1)
            self.assertEqual(f.notify_due(db,date(2026,11,19))["sent"],0)
            self.assertEqual(send.call_count,1)
            self.assertIn("메일 발송하기",send.call_args.args[3])
        db.close()

    def test_reviewed_send_records_contact_once(self):
        db=database()
        c={"sender":"admin@samsung.com"}
        d=f.draft(db,1)
        payload={"recipient":d["recipient"],"subject":"근황 확인","body":"안녕하세요.",
                 "request_id":d["request_id"],"approval_code":"testing-long-secret"}
        with patch.object(f,"config",return_value=c),patch.object(f,"send_knox",return_value={"status":"api_accepted","message":"API 수락"}) as send:
            f.send_candidate(db,1,payload)
            with self.assertRaisesRegex(ValueError,"이미 발송 시도"):
                f.send_candidate(db,1,payload)
            self.assertEqual(send.call_count,1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM contact_history").fetchone()[0],1)
        self.assertEqual(get_talent(db,1)["status"],"접촉중")
        db.close()

    def test_wrong_approval_never_sends(self):
        db=database()
        d=f.draft(db,1)
        with patch.object(f,"config",return_value={"sender":"admin@samsung.com"}),patch.object(f,"send_knox") as send:
            with self.assertRaisesRegex(ValueError,"승인 코드"):
                f.send_candidate(db,1,{"recipient":d["recipient"],"subject":"안부","body":"내용",
                                           "request_id":d["request_id"],"approval_code":"wrong"})
            send.assert_not_called()
        db.close()

    def test_unsure_outcome_is_not_retried_or_logged_as_contact(self):
        db=database()
        d=f.draft(db,1)
        p={"recipient":d["recipient"],"subject":"안부","body":"내용",
           "request_id":d["request_id"],"approval_code":"testing-long-secret"}
        with patch.object(f,"config",return_value={"sender":"admin@samsung.com"}),patch.object(f,"send_knox",side_effect=ValueError("timeout")) as send:
            with self.assertRaises(ValueError):f.send_candidate(db,1,p)
            with self.assertRaisesRegex(ValueError,"이미 발송 시도"):f.send_candidate(db,1,p)
            self.assertEqual(send.call_count,1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM contact_history").fetchone()[0],0)
        self.assertEqual(db.execute("SELECT state FROM followup_send").fetchone()[0],"uncertain")
        db.close()

if __name__=="__main__":
    unittest.main()
