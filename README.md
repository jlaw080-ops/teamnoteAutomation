# Gmail → Obsidian 미팅노트 자동화

team@genspark.ai에서 보내는 Meeting Notes 이메일을 자동으로 감지하여 Obsidian 볼트에 마크다운 노트를 생성합니다.

## 주요 기능

- Gmail에서 `team@genspark.ai` 발신 Meeting Notes 이메일 자동 감지
- 이메일 본문을 구조화된 섹션(회의 개요, 주요 결정사항, 실행 항목 등)으로 파싱
- Obsidian 템플릿을 적용하여 마크다운 노트 자동 생성
- 중복 처리 방지 (state.json으로 처리 이력 관리)
- Windows Task Scheduler로 5분마다 자동 실행

## 사전 준비

### 1. Python 설치

Python 3.10 이상이 필요합니다.
- [python.org](https://www.python.org/downloads/)에서 다운로드
- 설치 시 "Add Python to PATH" 체크

### 2. Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 (예: `gmail-obsidian-sync`)
3. **APIs & Services > Library**에서 **Gmail API** 활성화
4. **APIs & Services > Credentials**에서:
   - **Create Credentials > OAuth 2.0 Client IDs** 선택
   - Application type: **Desktop app**
   - 이름 입력 후 생성
5. 생성된 OAuth 클라이언트에서 **Download JSON** 클릭
6. 다운로드한 파일을 `credentials/credentials.json`으로 저장

> **참고**: OAuth 동의 화면(Consent Screen) 설정이 필요할 수 있습니다.
> Testing 상태에서는 본인 Gmail 계정을 Test users에 추가하세요.

## 설치

```bash
# 1. 저장소 클론
git clone https://github.com/jlaw080-ops/teamnoteAutomation.git
cd teamnoteAutomation

# 2. (권장) 가상환경 생성
python -m venv venv
venv\Scripts\activate   # Windows

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 설정 파일 생성
copy config.example.yaml config.yaml
# config.yaml을 편집하여 볼트 경로 등 설정
```

## 설정

`config.yaml`을 열어 본인 환경에 맞게 수정합니다:

```yaml
gmail:
  credentials_path: "credentials/credentials.json"
  token_path: "credentials/token.json"
  sender_filter: "team@genspark.ai"        # 발신자 필터
  subject_prefix: "Meeting Notes:"          # 제목 필터

obsidian:
  vault_path: 'D:\ENERGINNO Dropbox\KIM JEEHEON\앱\remotely-save\Vault_jlaw80'
  template_path: 'D:\ENERGINNO Dropbox\KIM JEEHEON\앱\remotely-save\Vault_jlaw80\Meta\Base note template.md'
  note_filename_format: "{date} {title}.md"  # 노트 파일명 형식

polling:
  lookback_hours: 24     # 첫 실행 시 과거 몇 시간까지 검색
  max_results: 10        # 한 번에 처리할 최대 이메일 수
```

## 최초 실행

```bash
# 1. OAuth 인증 (브라우저가 열립니다)
python setup_credentials.py

# 2. 테스트 실행 (노트 파일을 생성하지 않고 파싱 결과만 확인)
python main.py --dry-run

# 3. 실제 실행
python main.py
```

## Windows Task Scheduler 설정 (자동 실행)

### PowerShell로 설정

```powershell
$action = New-ScheduledTaskAction `
    -Execute "C:\path\to\venv\Scripts\pythonw.exe" `
    -Argument "C:\path\to\teamnoteAutomation\main.py" `
    -WorkingDirectory "C:\path\to\teamnoteAutomation"

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask `
    -TaskName "GmailObsidianSync" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Gmail Meeting Notes to Obsidian 자동 동기화"
```

> `C:\path\to\`를 실제 설치 경로로 변경하세요.

### GUI로 설정

1. **작업 스케줄러** 열기 (Win+R → `taskschd.msc`)
2. **작업 만들기** 클릭
3. **트리거** 탭: 5분마다 반복 설정
4. **동작** 탭:
   - 프로그램: `C:\path\to\venv\Scripts\pythonw.exe`
   - 인수: `C:\path\to\teamnoteAutomation\main.py`
   - 시작 위치: `C:\path\to\teamnoteAutomation`
5. **조건** 탭: "AC 전원에서만 시작" 해제

## 생성되는 노트 예시

파일명: `2026-04-13 에너지노 정기회의.md`

```markdown
---
tags:
  - Daily
related:
상태:
생성일: "2026-04-13"
updated: "2026-04-13"
---
---

**Date**: 2026-04-13 | **Duration**: 54 mins

## 회의 개요

본 회의는 신규 인력(신나리 과장) 소개를 시작으로...

## 주요 결정사항

건축사 파트너십: 리건축사사무소와의 업무 협약을 끝으로...

## 다음 단계 및 실행 항목

### 김 박사:
베트남 시설 관련 인증서 및 기술 자료 확보...
```

## 문제 해결

### 로그 확인

```bash
type logs\automation.log
```

### 일반적인 문제

| 문제 | 해결 방법 |
|------|-----------|
| 인증 오류 | `python setup_credentials.py` 재실행 |
| 토큰 만료 | `credentials/token.json` 삭제 후 `setup_credentials.py` 재실행 |
| 볼트 경로 오류 | `config.yaml`의 `vault_path` 확인 (Dropbox 동기화 상태 확인) |
| 중복 노트 | `state.json`에서 처리 이력 관리됨. 같은 이메일은 재처리하지 않음 |
| 과거 이메일 일괄 처리 | `config.yaml`의 `lookback_hours`를 늘리고 `state.json` 삭제 후 실행 |
