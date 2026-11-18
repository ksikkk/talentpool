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

## 대시보드 v3 — 간결한 3개 KPI 및 직접 편집

- **전체 등록 인재**: 전체 후보 목록으로 필터링
- **핵심 관리**: 관리 관심도 값이 `핵심`인 인재만 필터링
- **접촉중**: **접촉 이력이 1건 이상 존재**하는 인재만 필터링 (관리 상태 텍스트와 무관)
- KPI 클릭 → 해당 목록; 같은 후보 재클릭 또는 빈 화면 클릭 → 상세 닫기
- 목록: 연구 분야, 성명, 소속, 직책, 관심/핵심 구분
- 상세: 성명·소속·직책·연구 분야·요약·적합성·이메일 주소, 접이식 출처 URL
- 직접 편집 및 저장 가능. 이메일은 기존 외부 전송 JSON에 없으므로 기본값은 공란이며 사내 담당자가 입력
- 관리 정보: 관리 상태·관심도·내부 관리 메모만 표시
- 기존 접촉 이력 조회·등록 기능은 계속 제공
- 핵심 인재 대상 메일 발송은 **아직 구현하지 않음**. 승인된 사내 메일 API 예제를 받은 뒤 구현 예정
- 직접 수정한 공개 프로필 필드는 재수신된 서명 JSON이 덮어쓰지 않도록 보호

**사내 PC 업데이트(기존 데이터 유지)**

```powershell
# 사내 승인된 프로젝트 디렉터리에서
Copy-Item .\internal_talents.db .\internal_talents_backup.db
git pull origin main
python -m unittest discover -p "test_*.py" -v
python -m uvicorn viewer:app --host 127.0.0.1 --port 8090
```

기존 프로젝트를 실행하던 PowerShell에서 `INTERNAL_VIEW_PASSWORD` 설정을 유지하세요. **실제 DB가 별도 위치라면 먼저 `INTERNAL_DB_PATH`를 확인**하고 그 파일을 백업하세요. 신규 컬럼은 기존 데이터 삭제 없이 자동 추가됩니다. 기존에 입력된 담당자/후속조치 값은 DB에 남아 있지만 새 UI에는 표시하지 않습니다. 관리 화면은 로컬 접속만을 전제로 합니다.

## 대시보드 v4 — 열람/수정 분리 및 연구 분야 현황

- 인재 미선택 시 인재 목록이 전체 너비로 표시됩니다. 인재 선택 시 오른쪽 상세 패널이 나타납니다.
- 상세 정보는 기본 읽기 전용. `수정` 클릭 후에만 변경 가능하며 `저장` 또는 `취소`를 사용합니다.
- 사내 관리 정보와 접촉 이력은 각각 펼치기/접기 패널 안에 있습니다. 접촉 이력은 기존처럼 추가할 수 있습니다.
- 분야별 현황: DB의 `domain` 값을 기준으로 분야별 인재 수와 막대 표시, 카드 클릭으로 필터링. 여러 분야가 한 문자열에 적힌 경우 **현재는 하나의 분류**로 집계됩니다.
- 인재 목록: 성명, 소속, 직책, 연구분야, 관심/핵심 표시.
- 기존 세 KPI(전체 등록 인재/핵심 관리/접촉중)와 목록 필터는 유지.
- 화면 파일만 변경했으며 신규 DB 마이그레이션은 필요하지 않습니다.

업데이트 (기존 PowerShell 프로젝트 폴더):
```powershell
git pull origin main
python -m unittest discover -p "test_*.py" -v
python -m uvicorn viewer:app --host 127.0.0.1 --port 8090
```

서버가 이미 실행 중이면 `Ctrl+C`로 먼저 종료하고, 브라우저는 `Ctrl+F5`로 새로고침하세요. 실제 데이터와 테스트 DB는 GitHub에 올리지 마세요.

## v5 — 발굴 요청 분야별 대시보드 + 공개 직업용 이메일

**분야 분리**
- 인재 목록의 `연구분야`는 외부 검색에서 수집한 후보 개인의 세부 전문 분야(`domain`)를 그대로 표시합니다.
- 상단 **발굴 요청 분야별 현황**은 해당 인재를 찾을 때 사용자가 질문한 상위 분야(`requested_field`)를 기준으로 집계합니다.
- 같은 인재가 서로 다른 발굴 분야에서 선택되어 들어오면 중복 인재를 만들지 않고 `talent_field` 테이블에 두 분야를 연결합니다. 따라서 분야별 합계는 전체 고유 인재 수보다 클 수 있습니다.
- 과거 v4.1까지 받은 메일에는 `requested_field`가 없으므로 **기존 인재는 '미분류'**로 남을 수 있습니다. 이를 임의로 세부 연구 분야로부터 추론하지 않습니다. v5에서 다시 발굴·전달하면 분야가 연결됩니다.

**이메일 주소**
- 외부 Talent Scout v5는 기관 공개 홈페이지 등에서 직접 확인 가능한 직업용 이메일만 수집하도록 요청합니다.
- `email`과 `email_source`를 추가로 전달합니다. 이메일의 공개 근거 URL은 기존 `sources` 목록에도 포함되어야 합니다.
- 이메일 주소가 근거와 함께 확인되지 않으면 공란으로 유지합니다. 이전의 수동 입력 이메일은 유지하고 비어 있을 때만 신규 수집값을 채웁니다.
- 이 확인은 주소 형식과 링크 연결 조건에 대한 검사이며 **URL 원문에 실제로 이메일이 기재돼 있는지는 담당자가 검토**해야 합니다.
- 서명 검증, 기존 JSON 호환 및 사내 데이터의 외부 전송 금지는 유지됩니다.

**배포 순서**: 먼저 사내 수신 프로그램을 `git pull`로 업데이트하고 테스트하세요. 그다음 갤럭시탭 외부 Talent Scout v5를 설치합니다. 먼저 사내 수신기를 업데이트하면 이전 버전과 새 버전의 JSON을 모두 수신할 수 있습니다.

```powershell
# 사내 프로젝트 경로에서, 실제 사용 DB를 먼저 백업
Copy-Item .\internal_talents.db .\internal_talents_backup_before_v5.db
git pull origin main
python -m unittest discover -p "test_*.py" -v
python -m uvicorn viewer:app --host 127.0.0.1 --port 8090
```

사내 DB 경로를 `INTERNAL_DB_PATH`로 별도 지정했다면 해당 실제 파일을 백업하세요. 기존 `receiver.py --once`와 메일 계정 환경변수 설정은 동일합니다.
