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

## 실행 오류 수정: "Could not automatically identify a private LAN IPv4 address"

회사에서 관리하는 Windows PC의 IP가 일반적인 사설 IP 범위 밖이거나 여러 어댑터가 존재하면 기존 `launch.py`가 중단되었습니다. 업데이트된 `run.bat`은 현재 Windows의 실제 네트워크 구성에서 IPv4 후보를 찾습니다.

```powershell
git pull origin main
```

그다음 **`run.bat`을 더블클릭**하세요. 네트워크 주소가 여러 개 발견되면 숫자로 표시됩니다. 기본 주소가 맞으면 Enter만 누르면 됩니다. 화면에 `Share: http://IP:8090`이 나오면 그 주소를 동료에게 알려주세요.

비밀번호가 없는 테스트 구성인 만큼, 기본 허용 범위는 **서버 PC와 같은 /24 네트워크(실제 네트워크가 더 좁으면 그 범위)**입니다. 사내 다른 서브넷에 있는 동료에게도 공개해야 한다면 회사 IT 승인 하에 정식 인증 및 네트워크 정책을 설계해야 합니다. 외부 인터넷, 포트포워딩, 공용 터널은 지원하지 않습니다.

Windows 네트워크 프로필이 Public인 공인 IP는 자동 공유하지 않습니다. 이때는 회사 IT를 통해 승인된 서버 네트워크에서 실행하세요. Windows 방화벽에서 인바운드 TCP 8090을 허용하지 않았다면 주소를 알아도 다른 PC에서 접속되지 않습니다. 스크립트는 방화벽을 변경하지 않습니다.

```powershell
python -m unittest test_launch -v
```

## 간편 공유 실행 (people 저장소 실행 방식 참고)

현재 권장 실행 명령은 **`python app.py`**입니다. `ksikkk/people`의 `serve --share-edit`와 동일하게, 서버는 `0.0.0.0:8090`에 바인딩하고 실행 PC의 IPv4 후보를 출력합니다. IP 자동 발견에 실패하더라도 서버는 정상 실행을 계속합니다.

```powershell
# talentpool 폴더에서
git pull origin main
python -m unittest discover -p "test_*.py" -v
python app.py
```

실행창의 `Other PC: http://실행PC-IP:8090` 주소를 동료에게 알려주세요. 주소가 여러 개면 실제 회사망 주소를 선택하세요. 표시되지 않으면 실행 PC에서 `ipconfig`로 확인합니다. **다른 직원도 별도 설치 없이 같은 URL로 접속**합니다. 다만 회사 방화벽/네트워크가 TCP 8090을 허용해야 하며, 정책을 우회하지 않습니다.

비밀번호 없는 공동 관리이므로, IP와 포트에 도달 가능한 사용자는 조회·수정·삭제할 수 있습니다. 사내 승인 테스트에 한정하세요. 실제 채용 데이터 운영에는 사용자 인증·접근권한·HTTPS가 필요합니다. `run.bat`도 내부적으로 동일 `launch.py`를 사용하지만, 실행 방식은 `python app.py`를 권장합니다. 과거 `start_lan.ps1`은 더 이상 필요하지 않습니다.

## 월간 공개 전문 인재 프로필 변경 점검 (Talent Scout v6)

**데이터 경계**: 외부 Talent Scout의 공개 직업 프로필만 외부 OpenAI API의 입력으로 사용합니다. 이 사내 앱은 내부 기록을 외부로 전송하지 않고, 외부 AI를 호출하지도 않습니다.

갤럭시탭 외부 앱이 30일 단위로 공개 소속/직책/전문 분야/공개 직업용 이메일을 재검색합니다. 점검 결과는 `[TALENTPOOL-REFRESH]` 메일과 `talentpool-refresh.json` 서명 첨부파일로 `jobinfo@samsung.com`에 보내집니다.

**사내 수신**

```powershell
git pull origin main
python -m unittest discover -p "test_*.py" -v
python receiver.py --once
python app.py
```

메일 수신 프로그램은 이전의 `[TALENTPOOL-IMPORT]` 인재 등록 메일을 계속 처리합니다. 신규 `[TALENTPOOL-REFRESH]` 보고서는 별도의 `refresh_batch` 및 `pending_refresh` 테이블에 저장됩니다.

사내 웹 화면 상단의 **월간 정보 점검**에서 새로 확인된 공개 정보와 기존 정보, 공개 출처 URL을 나란히 볼 수 있습니다.

**보수적 업데이트 정책:** AI가 발견한 변경 제안은 메일 서명 검증을 통과하더라도 인물 동일성·출처 검증 전에는 사내 기본 인재 프로필이나 내부 관리 메모를 자동 덮어쓰지 않습니다. 이 버전은 **검토 대기 목록**까지만 구현했습니다. 검증 후 승인·반려 UI는 후속 개발 대상입니다.

점검 메일에 사람이 보낸 새 임의 명령이나 사내 인재 기록이 포함되어도 외부 AI 호출 기능은 없습니다. 인증정보와 DB 파일은 GitHub에 업로드하지 마세요.

## v7 — 자동 메일 수신 + 인재 카드형 목록

- 외부 Talent Scout v7은 **검색된 신규 후보 전원**을 `발굴 인재 Pool`에 저장하고 `jobinfo@samsung.com`으로 서명 JSON을 자동 발송 시도합니다.
- 후보를 `관심 인재 Pool`로 선택하는 단계는 **외부 앱에서만** 사용자의 명시적 조작으로 처리합니다. 사내에서는 기존처럼 발굴 인재 전원이 등록됩니다.
- 사내 `python app.py` 실행 중에는 **기본 300초(5분)** 간격으로 `receiver.poll_once()`가 자동 실행됩니다. 이전처럼 매번 `python receiver.py --once`를 실행할 필요가 없습니다.
- POP3 계정이 설정되지 않으면 자동 수신은 비활성화되며, 서버는 계속 실행되고 콘솔에 설정 안내를 표시합니다.
- 첫 실행 시 수신된 모든 메일을 지우거나 읽음 처리하지 않습니다. `incoming_batch`의 배치 ID로 중복 등록을 방지합니다.
- 인재 목록을 입체감 있는 **반응형 카드 그리드**로 변경했습니다. 연구 분야, 이름, 소속, 직책, 관심도를 읽기 쉽게 배치합니다. 기존 프로필 수정·접촉 이력은 유지됩니다.

### 사내 PC 최초 1회 자동 수신 계정 설정 (Windows PowerShell)

**승인된 Windows 계정**에서 `talentpool` 폴더로 이동해 다음 명령을 실행하세요.

```powershell
.\setup_mail.ps1
```

- 본인에게 사용 권한이 있는 **POP3 메일 계정의 싱글아이디**
- 승인된 외부 발신 이메일
- POP3 비밀번호
- 갤럭시탭 Talent Scout에서 사용하는 **동일한 HANDOFF_SECRET**

을 입력합니다. 비밀번호와 비밀키는 Windows 계정에 연결된 DPAPI 보호 형식으로 **`mail_credentials.local.json`에 저장**합니다. 이 파일은 **Git에서 제외**해야 하며, 다른 사용자 계정이나 다른 PC로 복사해서는 안 됩니다. 회사 승인된 비밀 저장소가 별도로 있다면 그 방식을 우선 사용하세요.

그다음부터 서버 실행만 하면 됩니다.

```powershell
git pull origin main
python -m unittest discover -p "test_*.py" -v
python app.py
```

웹 화면의 `/api/mail-status`는 자동 수신 활성화 여부와 마지막 실행 결과의 **건수만** 표시하며 인증정보나 인재 내용은 출력하지 않습니다. `POP3_POLL_SECONDS`로 수신 간격을 변경할 수 있지만 최소 60초이며 기본은 300초입니다.

**보안:** 현재는 사내망에서 접근 가능한 사용자에게 로그인 없이 편집·삭제 권한이 제공되는 테스트 모드입니다. 실제 인재·연락처 정보가 포함되므로 회사 SSO, 사용자별 역할, HTTPS와 내부 네트워크 접근 정책의 승인을 거쳐 운영하세요. `python app.py` 창이나 서버 PC가 꺼지면 자동 수신도 멈춥니다.

## v8 — 인재 중복 검토 및 출처 근거 표시

기존 POP3·HMAC JSON 수신 방식과 DB, 수정/삭제/접촉 기록을 유지하면서 인재 신원 식별을 보수적으로 변경했습니다.

- `identity_quality.py`: ORCID·Google Scholar·LinkedIn·ResearchGate의 **개인 프로필 ID**를 식별 단서로 활용합니다. DOI나 논문 공동저자 페이지는 개인 ID로 취급하지 않습니다.
- 프로필 ID와 이름이 같이 일치하거나 모든 핵심 정보·출처가 동일한 **기존 기록**이면 기존 레코드를 재사용할 수 있습니다. 다른 이름/ID 또는 동일 이름·소속만 발견되면 자동 병합하지 않습니다.
- 불확실한 신규 수신 후보는 `duplicate_review` 테이블에 따로 기록하고 기본 인재 DB에 자동 등록하지 않습니다. 배치 ID로 중복 메일 처리는 계속 방지합니다.
- 사내 화면 **중복 후보 검토**에서 수신 후보 및 기존 후보의 공개 근거를 비교하고 ‘동일 인재 → 추가 등록 생략’ 또는 ‘별도 인재 → 별도 등록’을 수동 선택합니다.
- **근거 품질**은 공개된 URL 종류와 근거 구성의 완성도를 나타내는 참고 지표입니다. 링크 본문을 실제로 열어 사실 확인을 끝냈다는 뜻이 아닙니다. 출처 원문, 최근 소속 및 논문 저자 일치 여부는 담당자가 확인하세요.
- 사내 데이터·메모·접촉 이력·비밀번호는 외부 Talent Scout 또는 공개 GitHub로 전송하지 않습니다. 메일 내용·실제 DB 파일은 절대 커밋하지 마세요.

업데이트:
```powershell
# 사용 중인 실제 DB 파일을 먼저 백업한 뒤
git pull origin main
python -m unittest discover -p "test_*.py" -v
python app.py
```

기존 DB는 자동 변경 시 추가 테이블만 생성합니다. 기존 후보를 자동 병합하거나 삭제하지 않습니다. 신규 이메일이 검증되어도 중복 확정 전에는 해당 후보의 자동 등록을 보류합니다.

## v9 — 월간 변경 자동 반영 + 사내 관리 UI 간소화

**월간 자동 갱신**: 갤럭시탭 Talent Scout의 관심 Pool에서 생성한 서명 메일 `[TALENTPOOL-REFRESH]`가 사내 POP3로 도착하면, 실행 중인 `python app.py`가 기존처럼 5분 주기로 수신하고 충돌 없는 변경은 사내 DB에 즉시 반영합니다. **담당자 승인 버튼은 필요 없습니다.**

조건:
- HMAC 검증을 통과한 메일만 처리
- 같은 이름·기존 소속으로 기존 DB에서 단 한 명이 식별될 것
- 외부 보고서의 연구자 공개 프로필 URL 또는 고유 ID가 기존 프로필의 근거와 연결될 것
- 이전 값이 사내 DB 값과 일치하고, 수동으로 수정한 항목은 아닐 것
- 공식 교육·연구기관/공공기관/연구자 식별정보 도메인에 근거가 있을 것
- 같은 항목에 대해 충돌하는 여러 변경 제안이 없을 것

모두 통과하면 `org`, `headline`, `domain`, `email`만 업데이트하며 변경 시각을 기록합니다. 통과하지 못하면 **프로필을 변경하지 않고** `applied_refresh` 테이블의 `result`에 보류 사유를 남깁니다. 서명이나 공식 도메인이 실제 내용의 사실 여부를 보증하지는 않습니다. 회사 개인정보 운영 기준에 따른 감사를 권장합니다. 사내 접촉 기록·내부 메모·관심도는 자동 수정하지 않습니다. **이미 수신 완료한 과거 refresh_batch는 중복 처리되므로, 갱신된 공개 정보는 새 점검 메일로 검증하세요.**

**화면 변경**
- 발굴 요청 분야별 현황: 바 그래프 삭제, 진한 전체 분야 카드와 밝은 분야별 숫자 카드를 구분
- 월간 정보 점검 메뉴 제거 (기존 기록 테이블은 보존)
- 관리 상태: `검토중`, `접촉중`, `보류`, `종료` 네 가지
- 상태·관심도·메모: 상세 패널 상단 `사내 관리 ▼`에서 편집 및 저장. 세부 프로필의 일반 `수정` 버튼과 분리
- 접촉 이력: 상단 `접촉 이력` 버튼에서 팝업 조회·추가
- 기존 데이터와 연락 기록 보존; 이전 상태값은 `검토중`으로 정리

**사내 PC 적용**
```powershell
# 실제 사용 DB 경로를 먼저 확인하고 백업하세요.
Copy-Item .\internal_talents.db .\internal_talents_backup_before_v9.db
git pull origin main
python -m unittest discover -p "test_*.py" -v
python app.py
```

서버 프로세스는 먼저 종료한 후 재실행하세요. 사내 POP3 계정 설정은 기존 것을 사용하며, 외부 Talent Scout는 v10 이상 기존 앱을 그대로 사용합니다. 메일 송신 형식은 변경하지 않았습니다.

외부 네트워크로 사내 인재 데이터 전송 기능은 추가하지 않았습니다. 다중 사용자 실운영 전에는 사내 인증·역할별 접근제어 및 데이터 백업/감사 정책을 보완하세요.

## 관리 현황 팝업 및 관심도 배지 표시 수정

- 인재 상세 오른쪽 위 `사내 관리` 버튼을 **`관리 현황`**으로 변경했습니다.
- 클릭하면 본문 아래 펼침 영역이 아니라 **접촉 이력과 같은 팝업**에서 관리 상태·관심도·내부 관리 메모를 수정·저장합니다. 팝업 오른쪽 닫기 또는 배경 클릭으로 닫습니다.
- 카드 우측 배지는 `핵심/높음/보통/낮음/미분류`를 **DB에 저장된 관심도 그대로** 표시합니다. 일괄적으로 `관심`으로 표시하지 않습니다.
- DB, POP3 메일 수신, 기존 인재·접촉 이력 형식은 변경하지 않았습니다.

반영:
```powershell
git pull origin main
python app.py
```
기존 서버를 먼저 `Ctrl+C`로 종료하세요. 브라우저는 `Ctrl+F5`로 강력 새로고침해 주세요.

## 관리 상태·관심도별 상단 대시보드 및 접촉 이력 자동 상태 전환

- 상단 전체 인원 카드 아래에 **관리 상태별 현황**(`접촉중`을 큰 강조 카드, `검토중`/`보류`/`종료`)과 **관심도별 현황**(`핵심`을 큰 강조 카드, `높음`/`보통`/`낮음`/`미분류`)을 표시합니다.
- 각 숫자 카드를 클릭하면 인재 목록이 해당 상태나 관심도로 필터링됩니다. '전체 등록 인재' 클릭 시 전체 보기로 복귀합니다.
- **접촉 이력 저장 시**, 해당 인재의 현재 상태가 `검토중`이면 동일 DB 트랜잭션 안에서 `접촉중`으로 자동 변경됩니다.
- 현재 상태가 `접촉중`, `보류`, `종료`이면 이력을 추가해도 상태를 변경하지 않습니다.
- 기존 접촉 이력, 관심도, 내부 메모 및 발굴 분야 집계는 유지됩니다.
- 추가 테스트: `test_management.py`의 검토중 전환, 보류/종료 보호, 접촉중 유지 확인.

적용 전 서버를 종료하고 필요 시 DB를 백업한 후 `git pull origin main`을 실행하고 `python -m unittest discover -p "test_*.py" -v`로 테스트한 다음 `python app.py`를 실행합니다.


## 핵심 인재 6개월 근황 확인 알림 및 승인 후 메일 발송

이 기능은 `ksikkk/learning`의 `mail_service.py`에 있는 **사내 Knox 메일 API 구조**(Authorization·System-ID, HTML 메일, 사용자 지정 사내 발신자, 단일 요청·불확실한 응답 자동 재시도 금지)를 참고했습니다. **기본값은 알림 자동 발송 꺼짐**입니다.

### 동작

1. 사내 인재 Pool에서 관심도가 `핵심`이고, 관리 상태가 `보류` 또는 `종료`가 아닌 인재를 확인합니다.
2. 실제 등록된 접촉 이력의 **가장 최근 날짜**로부터 **달력상 6개월** 경과한 경우에만 점검 대상으로 표시합니다. 접촉 이력이 없는 인재는 제외합니다.
3. 자동 알림을 활성화하면 서버 시작 시 1회 및 실행 중 24시간마다 확인합니다. 같은 **인재 + 마지막 접촉일** 조합으로 알림 메일을 중복 발송하지 않습니다.
4. 지정된 사내 알림 수신자에게 `[Talent Pool] 핵심 인재 6개월 접촉 점검` 메일과 **메일 발송하기** 버튼을 보냅니다. 버튼은 사내 웹 페이지 `/followups?talent_id=...`로 이동합니다. 버튼 클릭 자체는 **인재에게 메일을 보내지 않습니다.**
5. 담당자가 해당 인재의 **사전에 등록된 업무용 이메일**을 확인하고, 제목·본문을 자유롭게 고친 다음 **발송 승인 코드 입력 + 최종 확인**을 누르면 사내 Knox 메일 API를 한 번 호출합니다.
6. 메일 API가 HTTP 2xx를 반환하면 `followup_send`에 `accepted`를 기록하고 `contact_history`에 이메일 접촉 이력을 자동 추가합니다. 이는 **메일 서버 API 수락**이며 실제 수신/열람을 보증하지는 않습니다.
7. 새로운 접촉 이력에 따라 다음 6개월 기산일이 자동 변경됩니다. API 연결 오류·시간 초과 등 발송 결과가 불명확할 경우 `uncertain`으로 기록하고 자동 재발송하거나 접촉 이력을 추가하지 않습니다. 발신함 확인 후 재처리하세요.

### 처음 설정하는 방법 (사내 PC 전용)

`pip install -r requirements.txt`로 `requests`를 설치합니다.

1. `followup_mail.example.json`을 **`followup_mail.local.json`**으로 복사합니다 (이 파일은 `.gitignore`로 GitHub 업로드에서 제외됨).
2. `ksikkk/learning`에서 정상 동작 중인 메일 API 승인 정보를 참고하여 `knox_api_url`, `Authorization`, `System-ID`, `verify_tls`를 입력하세요. 인증서 검증은 기본 `true`입니다. 실제 비밀값을 GitHub에 넣지 마세요.
3. `sender`에는 회사 API에서 발송 승인된 내부 메일 주소, `notify_email`에는 **6개월 알림을 받을 담당자의 정확한 사내 메일 주소**를 입력합니다. `base_url`에는 **실제 사내 PC IPv4 주소**를 `http://192.168.x.x:8090` 형태로 입력합니다. 해당 사내 주소가 변경되면 링크가 작동하지 않으므로 다시 설정하세요.
4. 아래 PowerShell 예시에서 **별도 발송 승인 코드**를 정하고, 서버를 같은 PowerShell 세션에서 실행합니다. 승인 코드는 최소 10자이며 외부에 공유하지 마세요.

```powershell
$env:FOLLOWUP_APPROVAL_CODE = "여기에_본인만_아는_길고_고유한_코드"
# 먼저 알림 없이 내부 화면과 발송 초안만 테스트
$env:FOLLOWUP_NOTIFY_ENABLED = "0"
python app.py
```

웹에서 **핵심 인재 접촉 점검**으로 들어가 기한이 지난 인재와 메일 초안을 확인합니다. 처음에는 지정한 테스트 사내 주소와 테스트 인재의 이메일로 API 동작을 검증하세요. 인재에게 테스트 메일이 잘못 나가지 않도록 실제 후보 이메일 대신 허가받은 테스트 주소를 사용하세요.

실제 자동 알림을 활성화할 때에만 서버를 종료하고 다음 환경변수를 설정하여 다시 실행합니다.

```powershell
$env:FOLLOWUP_NOTIFY_ENABLED = "1"
python app.py
```

**주의:** `FOLLOWUP_NOTIFY_ENABLED=1`로 서버를 시작하면 이미 6개월 이상 지난 대상자에게 즉시 알림이 발송될 수 있습니다. 활성화 전에 `/followups` 목록과 수신 주소를 확인하세요. 사내 PC가 꺼져 있거나 프로그램이 실행 중이지 않으면 정기 점검도 실행되지 않습니다. 사내 SMTP/POP3 수신 설정과는 별도로 작동하며 외부 Talent Scout에는 변경이 없습니다.

**접근 통제:** 현 사내 웹앱은 LAN 접근 시 사용자 인증이 없는 상태입니다. 인재 발송에는 승인 코드가 필요하지만 목록·초안 열람까지 인증을 대신하지는 못합니다. 회사 운영 적용 전에 접속망·승인 코드·발신 권한 정책을 확인하세요. 민감한 인재 정보는 저장소에 업로드하지 마세요.


### 메일 주소를 사내 화면에서 변경하는 방법

**설정 파일 위치**: 이 저장소를 `git clone`한 사내 PC의 **`talentpool/followup_mail.local.json`** 입니다. GitHub에 이미 포함되어 있는 파일이 **아닙니다**. 보안상 `.gitignore`에 등록되어 있으므로 `git pull`을 해도 자동 생성되지 않습니다. 다음 명령으로 1회 생성하세요:

```powershell
# 'git pull'을 실행하는 talentpool 폴더에서 실행
Copy-Item .\followup_mail.example.json .\followup_mail.local.json
notepad .\followup_mail.local.json
```

생성한 파일에 승인된 사내 Knox API의 `knox_api_url`, `Authorization`, `System-ID`, `verify_tls` 및 실제 사내 PC의 `base_url`을 설정하세요. `sender` / `notify_email`은 초기값만 입력하고 나중에 **사내 웹 화면에서 변경**해도 됩니다. **GitHub에는 인증값을 업로드하지 마세요.**

사내 `python app.py` 실행 후, 상단의 **핵심 인재 접촉 점검 → 메일 주소 설정 → 주소 설정 열기**에서 다음 항목을 변경할 수 있습니다.
- **발송자 사내 메일 주소** (`sender`): Knox API에서 승인된 `@samsung.com` 계정
- **6개월 알림 수신 주소** (`notify_email`): `@samsung.com` 담당자 메일 주소

저장을 위해서는 서버 프로세스에 설정한 `FOLLOWUP_APPROVAL_CODE` 입력이 필요합니다. 설정 화면의 API 인증 정보와 승인 코드는 조회되지 않습니다. `followup_mail.local.json`의 나머지 값은 보존됩니다.

**메일 작성창의 인재 수신 주소(1회성)**: 핵심 인재 접촉 점검 → 해당 인재 **메일 발송하기** → 작성창의 **받는 사람** 주소를 직접 수정 → 발송 승인 코드 입력 → **최종 확인 후 메일 발송**. 수정된 수신 주소는 **해당 발송 요청에만 사용**하고, 인재 프로필의 `email` 필드는 변경하지 않습니다. 실제 발송 주소는 발송 시도 기록(`followup_send`)과 접촉 이력에 남깁니다. 인재 프로필 이메일을 영구적으로 고치려면 기존 **인재 상세 및 관리 → 수정** 기능을 사용하세요.

주소를 변경해도 이미 보낸 알림 메일을 새 수신자에게 다시 보내지는 않습니다. 같은 마지막 접촉일에 대한 알림 중복 차단은 유지됩니다. 새 근황 확인 주기가 도래하면 변경된 주소를 사용합니다.

**보안:** 현재 사내 웹 시스템은 LAN 사용자 인증 없이 공유 중입니다. 주소 변경과 메일 발송에는 승인 코드가 필요하지만, **HTTP 접속에서는 승인 코드가 통신 중 보호되지 않습니다**. 보안 검토 후 사용자 인증과 HTTPS를 도입하고, 승인된 사내 계정만 사용해야 합니다.


## 수신자 검색형 일반 메일쓰기

인재 Pool 관리 화면 상단 **메일쓰기** 버튼 또는 선택한 인재 상세의 **메일쓰기** 버튼을 누르세요.

1. **성명·소속·직책·연구 분야**로 사내 인재 Pool을 검색합니다. 검색 결과의 성명·소속·현재 등록 메일을 확인하고 한 명을 선택합니다.
2. 선택한 인재의 등록 이메일이 받는 사람 기본값으로 채워집니다. **받는 사람 주소를 수정해도 인재 DB의 이메일은 변경되지 않으며 이번 발송 한 번에만 적용됩니다.** 등록 메일이 없는 후보도 주소를 직접 입력할 수 있습니다.
3. **제목·본문**을 직접 수정하고 `FOLLOWUP_APPROVAL_CODE`를 입력한 뒤 **최종 확인 후 메일 발송**을 누릅니다. 인재 검색·초안 작성만으로는 발송되지 않습니다.
4. `learning`에서 참고한 기존 사내 **Knox 메일 API**를 사용하며, 실제 승인 정보는 `followup_mail.local.json`에 보존합니다. API 2xx 수락 시 `direct_mail_send`에 요청 이력을 저장하고 사내 접촉 이력에 실제 발송 수신자·제목을 기록합니다.
5. 동일 `request_id`로 다시 발송하지 않습니다. 네트워크 오류·타임아웃처럼 전송 결과가 불확실한 경우 **자동 재전송이나 접촉 이력 자동 등록을 하지 않으므로** 발신함 확인 후 조치해야 합니다.

**안전 규칙:** 인재 프로필이 삭제되었거나 관리 상태가 `보류`/`종료`이면 일반 메일 발송을 차단합니다. 연락 상태가 `검토중`이면 API 수락 후 기존 규칙에 따라 `접촉중`으로 변경됩니다. 기본 6개월 자동 알림 로직과는 별개이며, 어느 기능도 외부 Talent Scout에 사내 정보를 전송하지 않습니다.

현재 사내 웹은 별도 로그인 없이 LAN에서 수정 가능하므로 **개인별 인증/권한과 HTTPS 검토를 거친 뒤** 실제 인재 대상 발송을 운영하세요. 메일 API 성공은 서버 수락이지 수신자에게 도달했음을 보증하지 않습니다.

## 메일 발송 승인 코드 제거 (최신)

- `FOLLOWUP_APPROVAL_CODE`는 더 이상 필요하지 않습니다. 메일 작성 화면과 메일 주소 설정에서 코드 입력란을 제거했습니다.
- **일반 메일쓰기**와 **핵심 인재 6개월 근황 확인 메일**은 수신자·제목·본문을 작성하고, 최종 확인 팝업에서 확인 후 사내 Knox API에 전송 요청합니다.
- 발송자/알림 수신 주소 설정 저장도 승인 코드 없이 가능합니다. `followup_mail.local.json`의 Knox `Authorization`, `System-ID` 등 인증 정보는 그대로 사내 PC에 보관되며, 해당 설정 파일 자체는 여전히 필요합니다.
- 수신자 이메일을 수정해도 인재 DB의 이메일은 변경되지 않습니다.
- API 수락 후 접촉 이력 자동 등록, `검토중 → 접촉중` 자동 전환, 요청 ID 중복 차단, 결과 불확실 시 재전송 금지 기능은 유지됩니다.
- **보안 주의:** 현재 이 웹 시스템에는 사용자 로그인과 HTTPS가 없습니다. 승인 코드 제거로 **사내 웹 주소에 접속할 수 있는 누구나 메일을 발송하거나 발송자 주소 설정을 변경할 수 있습니다.** 회사에서 실제 인재에게 발송하려면 사내 인증, 권한 제어, HTTPS를 우선 적용하거나 사내망 방화벽으로 접속자를 제한하세요.

반영: 서버를 종료한 뒤 `git pull origin main` → `python app.py` → 브라우저 `Ctrl+F5`.
