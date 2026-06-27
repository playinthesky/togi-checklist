# CLAUDE.md

이 파일은 Claude Code(claude.ai/code 포함)가 이 저장소에서 작업할 때 참고하는 팀 공용 가이드입니다.

## 🔗 단일기준(SSOT) — 작업 전 먼저 확인

이 저장소를 여는 **모든 AI**는 작업 전 `playinthesky/kspeaks-agora` 레포의 다음 단일 진실을 참조한다:

- **6인 캠프 표준**: `AGENTS.md` (호칭·역할·통신 프로토콜)
- **숙의컨설팅 마스터**: `methodology/숙의공론컨설팅_AI시스템_마스터_v0.1.md` · SOC `methodology/SOC_숙의공론컨설팅_표준업무_정의서_v0.5.1.1.md`
- **용어 사전**: `knowledge/용어사전_v0.2.md` (새 용어 즉시 등재) · **지식 색인** `methodology/지식_카탈로그_색인_v0.1.md` (재질문 전 검색)
- **검증 규칙**: `methodology/AI팀_오류최소화_검증프로토콜_v0.1.md` — **검증 전 단정 금지, 링크 fetch 확인 후, 교차검증.**
- **DX/AX 통합 SSOT**: `docs/DX_업무_전수정리_v0.2.0.md` · 로드맵 `docs/DX_로드맵_v0.2.md` — 36개 영역 매트릭스 + 단기·중기·장기.
- **KDLB**(Korea Deliberative Leadership Brain — 숙의공론컨설팅 지능) `methodology/KDB_숙의공론컨설팅지능_정의서_v0.2.md` · **AX 좌표진단**(외부 클라이언트 5축 진단) `methodology/AX_좌표진단_프레임_v0.1.md` + 기계읽기 `methodology/ax_framework.yaml`

---

## 🚨 6인 캠프 표준 (필독)

이 저장소를 여는 **모든 AI**는 6인 캠프 명단·역할·통신 프로토콜을 준수한다. 단일 진실은 위 §SSOT.

### 6인 캠프 명단 요약

| 호칭 | 실체 | 주 역할 |
|---|---|---|
| **빙허각** | Claude Code (CLI/웹) | 오케스트레이션·저장소 작업 |
| **본승지** | claude.ai Cowork | 설계·협업·외부 응대 검토 |
| **소춘풍** | claude.ai Chat 데스크탑 | 빠른 응답·즉답 |
| **모별감** | claude.ai 모바일 | 외부 모바일 확인·즉시 결정 |
| **별동수** | OpenAI Codex | 실행·코드 작성·배포 |
| **구편수** | Google Antigravity | 실행·구글 통합·자동화 |

- **설계·검토**: Claude 4종 (빙허각·본승지·소춘풍·모별감) — 명세만 박고 코드 직접 짜지 않음
- **실행·관리·운영**: 별동수·구편수 — 코드·배포·인프라

### 메시지 서명 의무

모든 메시지·Issue·댓글·슬랙 끝에 본인 호칭 박을 것:
- `— 빙허각` / `— 본승지` / `— 소춘풍` / `— 모별감` / `— 별동수` / `— 구편수`

### 통신 — GitHub Issue 인박스 (`playinthesky/kspeaks-agora`)

| 인박스 라벨 | 주인 |
|---|---|
| `codex` | 별동수 |
| `antigravity` | 구편수 |
| `claude` | 빙허각·본승지·소춘풍·모별감 (제목 `[수신자]` 호명) |

---

## 프로젝트 개요

**togi-checklist** 는 청토지(청년농업인) 보수교육 행사용 체크리스트 웹앱입니다.
지회·직원 PIN 로그인 + 행사 준비 체크리스트 + Google Sheets 양방향 동기화.

- **언어/UI**: 한국어
- **데이터 저장소**: PostgreSQL (Render) / SQLite (로컬 폴백) + Google Sheets 동기화
- **배포**: Render (`render.yaml`, `Procfile`)

## 기술 스택

| 구분 | 사용 기술 |
|------|-----------|
| 백엔드 | Python 3.11, `http.server` 표준 라이브러리 |
| DB | PostgreSQL (`psycopg2-binary`) + SQLite 폴백 |
| 프론트 | 정적 SPA (`public/index.html`) |
| 동기화 | Google Apps Script (`google-apps-script.js`) |
| 배포 | Render (Python 3.11, free plan) |

## 디렉터리 구조

```
server.py            # 단일 파일 HTTPServer (인증·체크리스트·동기화 API)
public/
  ├ index.html       # SPA — 로그인·체크리스트·관리자 대시보드
  └ health.html      # 사이드 트랙 — 대사 액션 (BMR/TDEE)
google-apps-script.js  # Sheets 동기화 (doPost 수신)
render.yaml / Procfile / runtime.txt   # Render 배포 설정
```

## 핵심 개념

### PIN 기반 인증
지회 선택 → 직원 선택 → PIN 로그인 (`/api/login`, `/api/me`). 관리자 PIN 별도.

### Google Sheets 양방향 동기화
서버사이드 프록시 `/api/sync-sheets` → Apps Script `doPost` 웹앱 수신. CORS/SSL 우회.

### 소셜 로그인 (진행 중 — PR #3)
`oauth_providers.py` 신설. Kakao/Google/Naver OAuth 2.0. `staff` 테이블에 email/provider/provider_uid 마이그레이션.

## 환경변수

| 변수 | 용도 | 비고 |
|------|------|------|
| `DATABASE_URL` | PostgreSQL 연결 (Render) | 없으면 SQLite 폴백 |
| `SHEETS_WEBHOOK_URL` | Apps Script 웹앱 URL | Sheets 동기화 |
| `OAUTH_REDIRECT_BASE` | 소셜 로그인 콜백 베이스 | PR #3 머지 후 |
| `*_CLIENT_ID/SECRET` | Kakao/Google/Naver | PR #3 머지 후 |

## 협업 규칙

- **한국어로 응답**하고, UI 문구·주석도 기존 한국어 톤을 유지.
- **비밀번호·API 키·크레덴셜을 코드에 하드코딩하거나 커밋하지 마세요.** 항상 환경변수.
- 별도 테스트 프레임워크가 없습니다. 변경 후에는 최소한 앱이 import/기동되는지 확인.

## 브랜치 / PR

- 기능 개발은 별도 브랜치에서 진행, 완료 시 PR (기본 draft).
- Doc-only PR(CLAUDE.md·README·docs/) 은 운영 자산 0건일 때 빙허각 자동 머지 가능 (AGENTS.md §Doc-only PR 자동 머지 규약 준수).
- 그 외 PR은 대표님 명시 머지 신호 필요.

---

*이 파일은 모든 Claude 세션에서 자동으로 읽힙니다. 6인 캠프 표준·DX SSOT 갱신은 kspeaks-agora 단일 진실 참조.*
