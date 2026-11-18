# Internal Talent Pool (사내망 전용)

This code is designed for the Samsung intranet and does **not** upload, export, synchronize, or call external APIs with internal talent data. It reads a dedicated internal POP3 mailbox, imports **only** HMAC-signed JSON messages addressed to `jobinfo@samsung.com`, and offers a local browser viewer.

## Install (inside approved internal environment)

```bash
git clone https://github.com/ksikkk/talentpool.git
cd talentpool
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export POP3_HOST=pop3.samsung.net
export POP3_USER='싱글아이디를 직접 설정'
export POP3_PASSWORD='싱글비밀번호를 직접 설정'
export TRUSTED_SENDER='승인된 실제 송신 메일 주소'
export HANDOFF_SECRET='외부 v4와 동일한 충분히 긴 무작위 비밀키 24자 이상'
export INTERNAL_DB_PATH=./internal_talents.db
python receiver.py --init-db
python receiver.py --once
export INTERNAL_VIEW_PASSWORD='사내 뷰어 접속 비밀번호'
uvicorn viewer:app --host 127.0.0.1 --port 8090
```

브라우저: http://127.0.0.1:8090 . 사내 SSO·HTTPS·접근 통제 전에는 외부 인터페이스에 바인딩하지 마세요.

## Security and operation

- **No single-ID or password is stored in this repository.** Never commit env files, internal DB, credentials, raw emails, or real candidate data to GitHub.
- Use `git pull` for **code updates only** after internal security review. Whether GitHub is reachable/approved inside your corporate network must be verified.
- Based on provided POP3_SSL example: `pop3.samsung.net`. Configure credentials locally. A dedicated mailbox is preferred.
- Sender must match `TRUSTED_SENDER`, recipient `jobinfo@samsung.com`, subject starts `[TALENTPOOL-IMPORT]`, body starts `TALENTPOOL_JSON_V2`, and `X-Talentpool-Signature` must match HMAC SHA-256. Sender spoofing alone is not sufficient to import.
- Payload schema v2 contains public professional data only: name, organization, role, research field, location, summary, fit rationale, and HTTPS evidence links.
- Batch IDs are idempotent. Existing talent records are updated by identity key, not blindly duplicated.
- No messages are deleted from mailbox. Run `python receiver.py --once` manually or through an **approved internal** scheduler. Default scans latest 100; `POP3_SCAN_LIMIT` can increase it.
- This is an **independent SQLite test system**, not an adapter to your existing corporate talent database, which has not been provided. Use internal approval and an official DB/API interface for any later production integration.
- SMTP accepted != imported. Confirm import count from receiver output and local viewer.
- Viewer only runs locally and links to public source sites; opening them could make outbound requests **from the user's browser**. Do not open those links if policy forbids external access.
- There is no outgoing data connector. Still validate DNS/network policy, repository accessibility, and runtime dependencies with IT/security before production.
