import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from receiver import connect_db
from management import database, get_talent, edit_talent, add_contact, contacts, list_talents

class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=str(Path(self.folder.name)/"pool.db")
        self.patcher=patch.dict("os.environ",{"INTERNAL_DB_PATH":self.path})
        self.patcher.start()
        db=connect_db(self.path)
        db.execute("""INSERT INTO talent(identity_key,name,org,headline,domain,location,summary,why_fit,sources_json,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        ("sample-key","가상 인재","가상 연구소","책임연구원","HBM","한국","공개 연구","전문성","[\"https://example.org\"]","2026-01-01","2026-01-01"))
        db.commit()
        db.close()

    def tearDown(self):
        self.patcher.stop()
        self.folder.cleanup()

    def test_upgrade_existing_database_without_losing_people(self):
        db=database()
        t=get_talent(db,1)
        self.assertEqual(t["name"],"가상 인재")
        self.assertEqual(t["priority"],"미분류")
        db.close()

    def test_edit_and_filter(self):
        db=database()
        result=edit_talent(db,1,{"status":"접촉예정","priority":"핵심","owner":"채용 담당","internal_notes":"내부 검토","next_action":"후속 연락","next_action_date":"2026-12-01"})
        self.assertEqual(result["priority"],"핵심")
        self.assertEqual(len(list_talents(db,status="접촉예정",priority="핵심")),1)
        with self.assertRaises(ValueError):
            edit_talent(db,1,{"name":"변경 불가"})
        db.close()

    def test_contact_history(self):
        db=database()
        added=add_contact(db,1,"이메일","가상 안내","연락 내용","2026-11-18")
        self.assertIsInstance(added,int)
        self.assertEqual(contacts(db,1)[0]["subject"],"가상 안내")
        db.close()

    def test_mail_import_keeps_internal_notes(self):
        from receiver import import_mail
        from test_receiver import sample_mail, SECRET, SENDER
        db=database()
        edit_talent(db,1,{"internal_notes":"유지해야 할 내부 메모","priority":"핵심"})
        self.assertEqual(import_mail(db,sample_mail(),SECRET,SENDER),"imported")
        self.assertEqual(get_talent(db,1)["internal_notes"],"유지해야 할 내부 메모")
        db.close()

if __name__=="__main__":
    unittest.main()
