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

## v6 — 분류, 텍스트형 상세 조회, 수정 완료/삭제 및 승인된 다른 PC 접속

- 상세 정보의 `분류` 항목을 추가했습니다. 직접 수정 가능하며 기존 발굴 요청 분야(`requested_field`)는 별도로 보존합니다.
- 상세 조회 시 이름·소속·직책·연구 분야 등은 **일반 텍스트**로 표시합니다. 수정 버튼을 누르면 입력 박스로 전환합니다.
- 오른쪽 상세 패널 상단에 `수정`·`삭제`·`닫기`를 배치했습니다. `수정` 선택 시 `수정 완료`·`취소`로 전환됩니다.
- 삭제는 **soft delete**입니다. 목록·대시보드에서 제외하지만 DB의 접촉 기록과 원본은 남겨 오작동 시 복구할 수 있습니다. 외부 메일을 다시 수신해도 자동으로 재활성화하지 않습니다.
- 앱 자체의 로그인 비밀번호는 제거했습니다. **기본값은 여전히 해당 PC의 localhost에서만 접속 가능**합니다.
- 다른 PC에서 이용하려면 (1) IT 담당자가 승인한 사내망 범위, (2) Windows 방화벽의 승인된 PC/대역 인바운드 설정, (3) 접속 중인 사내 네트워크의 차단 정책을 확인해야 합니다.
- `INTERNAL_ALLOWED_CIDRS`에 승인된 **좁은 사설 네트워크 CIDR**을 명시해야 합니다. 공개망/광범위 대역은 허용하지 않습니다.
- 서비스에 로그인 인증이 없어졌으므로 **허용 IP 대역에 들어온 누구나 인재 정보를 보고 수정하거나 삭제할 수 있습니다**. 정식 업무 용도라면 회사 SSO 및 사용자별 접근 통제를 네트워크 앞단에 반드시 구성하세요.

### 설치

회사 정책상 허용된 환경에서만 진행합니다. 기존 서버를 `Ctrl+C`로 종료하고 실제 DB 파일을 백업하세요.

```powershell
git pull origin main
python -m unittest discover -p "test_*.py" -v
# 예: IT에서 승인한 192.168.25.0/24 대역만 허용. 실제 승인 대역으로 교체.
$env:INTERNAL_ALLOWED_CIDRS="192.168.25.0/24"
python -m uvicorn viewer:app --host 0.0.0.0 --port 8090
```

예시 주소 `192.168.25.0/24`를 그대로 사용하지 마세요. **관리 PC의 사설 IP와 다른 PC의 IP를 확인해 IT에서 허용한 CIDR**을 사용해야 합니다. Windows 방화벽에서도 **TCP 8090 인바운드를 승인된 원격 IP 범위에만** 허용해야 합니다. 인터넷 라우터 포트포워딩·공용 터널·공개 클라우드로 내보내면 안 됩니다.

서버 PC IP 확인: PowerShell에서 `ipconfig`. 다른 승인 PC의 브라우저에서 `http://<서버PC_사설IP>:8090`으로 접속합니다. 연결이 안 되면 회사 내부망/방화벽 정책을 IT팀에 확인하세요.

기존 환경변수 `INTERNAL_VIEW_PASSWORD`는 새 웹 서버 코드에서 사용하지 않습니다. POP3 수신용 비밀키와 인증 정보는 계속 필요합니다.

## v6.1 — 서버 PC의 실제 로컬 IP로 다른 승인 PC 접속

서버를 실행할 사내 Windows PC의 **실제 사설 IPv4를 자동 감지**하도록 `start_lan.ps1`을 추가했습니다. 이 스크립트는 앱 자체 로그인 비밀번호 없이 실행하지만, 원격 접속은 **명시적으로 허용한 사내 PC IP**로 제한합니다.

1. 기존 웹 서버를 종료하고 프로젝트 폴더에서 `git pull origin main`을 실행합니다.
2. 서버 PC가 사용할 로컬 IP를 자동 탐지해 자신만 접근 가능하게 실행하려면:

```powershell
.\start_lan.ps1
```

3. **다른 직원 PC까지 접속**시키려면 IT에서 승인된 해당 PC의 *사설 IPv4 주소*를 확인하고 실행합니다.

```powershell
.\start_lan.ps1 -AllowedClientIPs "10.10.20.31","10.10.20.32"
```

위 두 IP는 예시입니다. 실제로 승인된 직원 PC 주소로 교체하세요. 서버 IP는 자동 감지됩니다. 다수의 사설 네트워크 어댑터가 있어 자동 식별이 애매하다면 `ipconfig`로 확인 후:

```powershell
.\start_lan.ps1 -ServerIP "10.10.20.10" -AllowedClientIPs "10.10.20.31"
```

스크립트가 출력하는 `http://서버PC_IP:8090` 주소를 다른 직원에게 전달합니다. 별도 `INTERNAL_VIEW_PASSWORD` 설정은 필요하지 않습니다.

**IT/보안 선행 조건**: Windows 방화벽의 TCP 8090 인바운드를 승인된 PC에만 허용해야 하며, 서로 다른 PC 간 사내 네트워크 라우팅이 허용되어야 합니다. 스크립트는 방화벽을 자동으로 열지 않습니다. 사내 보안 규정상 익명 인재 조회·편집이 승인되지 않았다면 실행 전에 회사 SSO 및 권한 제어를 연동하세요. 브라우저와 앱 사이의 HTTP 통신은 암호화되지 않으므로 실제 인재 데이터가 오가는 정식 운영에는 사내 승인 HTTPS 역방향 프록시가 필요합니다. 이 스크립트는 제한된 사내 테스트 용도입니다. 공용 인터넷에 노출하지 마세요.

## v6.2 — IP와 포트만으로 접속하는 사내 LAN 공유

접속자 IP를 일일이 등록하지 않습니다. 서버 PC에서 실제 사설 IPv4를 자동 감지한 후 **공유 주소를 표시**합니다.

```powershell
git pull origin main
.\start_lan.ps1
```

다른 PC에서는 출력된 `http://서버-PC-IPv4:8090` 주소를 브라우저에 입력합니다. 자동 감지가 모호할 때만 `.\start_lan.ps1 -ServerIP "실제_사설IPv4"`를 사용하세요.

- 앱 로그인 비밀번호는 없습니다. 서버 실행기가 `TALENTPOOL_LAN_SHARE=1`을 설정하고 서버 PC의 사설 IP에 바인딩합니다.
- 사내 사설 IPv4(10/8, 172.16/12, 192.168/16)에서 연결한 사용자는 별도 사용자 등록 없이 접속할 수 있습니다. **사내망 라우팅과 Windows 방화벽 TCP 8090 인바운드 허용이 전제**입니다.
- 다른 컴퓨터에 인터넷 공개 접속을 제공하지 않습니다. 개인 PC나 외부 인터넷에 포트를 포워딩하거나 터널을 열지 마세요.
- **중요: 접속 가능한 누구나 인재 정보와 접촉 이력을 읽고 수정·삭제할 수 있습니다.** 익명 LAN 공유는 한시적 내부 검증으로만 사용하고, 운영 전에 사내 승인 SSO·접근 권한·HTTPS를 적용하세요.
- 사내 방화벽은 회사 IT·보안 규칙을 따라 설정합니다. 스크립트는 방화벽을 자동으로 열지 않습니다.

## 가장 쉬운 실행 방법: run.bat 더블클릭

서버 역할을 할 **사내 PC의 talentpool 폴더**에서 `git pull origin main`을 1회 실행하세요. 그다음부터 `run.bat` (또는 `실행.bat`)을 **더블클릭**하면 됩니다.

- 기존 FastAPI 웹 화면 그대로 사용합니다. Streamlit을 따로 설치할 필요가 없습니다.
- IP를 수동으로 지정하거나 `start_lan.ps1`을 사용할 필요가 없습니다.
- 실행 창에서 `Share: http://IP:8090` 주소를 확인해 동료에게 전달하세요.
- 서버 창을 닫거나 서버 PC를 종료하면 접속할 수 없습니다.
- 같은 사내망이어도 네트워크 분리·Windows 방화벽이 막으면 접속되지 않습니다. 임의로 보안을 우회하지 말고 IT 승인 범위를 확인하세요.
- 기존 비밀번호 입력은 없지만 사설망에서 접근 가능한 사용자에게 **조회/수정/삭제 권한이 모두 열려 있습니다**. 실제 채용 정보 운영 전에 사내 SSO·권한관리·HTTPS를 적용해야 합니다.
- `run.bat`은 Windows 방화벽, 네트워크 정책을 임의로 변경하지 않습니다.
