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

## 인재 관리 대시보드 v2 (사내 검증용)

기존 `receiver.py`, `internal_talents.db`를 유지합니다. `git pull origin main` 후 **기존 DB 파일을 삭제하거나 초기화하지 마세요.** `viewer.py`를 실행하면 SQLite에 관리 필드를 **추가하는 방식**으로 자동 마이그레이션합니다.

사내 Windows PowerShell (프로젝트 폴더에서 실행):

```powershell
git pull origin main
python -m unittest discover -p "test_*.py" -v
$env:INTERNAL_VIEW_PASSWORD="이_컴퓨터에서만_설정할_강한_비밀번호"
python -m uvicorn viewer:app --host 127.0.0.1 --port 8090
```

브라우저에서 `http://127.0.0.1:8090`에 접속합니다. 현재 HTTP Basic 인증의 사용자명은 임의의 비어 있지 않은 값이며, 암호는 `INTERNAL_VIEW_PASSWORD`입니다.

- 인재 이름·소속·기술 분야 검색, 상태·관심도 필터
- 인재 상세 프로필 및 검증 출처 링크
- 관리 상태: 검토대기/검토중/관심/접촉예정/접촉중/보류/종료
- 관심도: 미분류/핵심/높음/보통/낮음
- 담당자, 내부 관리 메모, 후속 조치 내용·날짜 직접 저장
- 접촉 이력: 이메일/전화/미팅/기타, 날짜·제목·메모
- 상단 요약 지표. 모든 정보는 **사내 로컬 SQLite DB**에서만 조회합니다.
- 서명된 신규 메일을 재수신해도 기존 관리 필드와 접촉 이력은 변경하지 않습니다.

보안: 승인된 사내 사용자만 로컬 PC에 접속하도록 하세요. 현재 MVP는 단일 공유 암호 방식이며 개별 사용자별 접근 권한·변경 이력·사내 SSO가 없습니다. 개인 메모나 접촉 기록에는 불필요한 민감 개인정보를 기록하지 마세요. 공식 채용 시스템 전환 전 권한 관리·감사 로그·개인정보 보유 기간 및 파기 정책을 마련해야 합니다.

코드 및 테스트에는 가상의 후보만 사용합니다. 실제 사내 DB·로그·비밀번호·메일 원문은 GitHub에 올리지 마세요.
