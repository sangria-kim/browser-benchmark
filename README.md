# Browser Benchmark

Chrome 실험 기능과 Chrome·Edge·Firefox·Brave·Whale·Opera·Vivaldi의 새 기능 및 주요 동작 변경을 공개 공식 자료로 추적하는 아카이브입니다. Windows와 Android를 우선하며, 제품 비교와 재현 가능한 벤치마크 후보를 기록합니다.

Brave·Whale은 기존 매 실행, Opera·Vivaldi는 주 1회 보조 관찰합니다. Safari는 제외합니다. 추가 4종의 실제 수집은 아직 미실행입니다.

## 현재 상태

- [릴리스 전체 항목 색인](releases/README.md): Chrome 156/157, Firefox 159·160 Beta, Edge 156의 명시된 공식 자료 범위.
- [PC](reports/pc/README.md) · [Mobile](reports/mobile/README.md) · [AI](reports/ai/README.md): 기존 날짜별 보고서의 업무별 색인.
- [Chrome flags](experiments/chrome/README.md): 2026-06-01 이후 about_flags.cc 1,169 commit, 938개 flag ID 이력. 설치본 검증·PM 선별은 미완료.
- [수집 범위와 남은 작업](docs/collection-status.md)을 확인하세요. 자동화 연결·메일 발송 상태는 이 문서 변경으로 바뀌지 않습니다.

## 읽기 전용 사용

```sh
git clone https://github.com/sangria-kim/browser-benchmark.git
cd browser-benchmark
git pull --ff-only
```

사내에서는 clone/pull로 열람합니다. 로컬 검토 자료는 저장소 밖에 보관하고 외부로 push하지 않습니다. 문서는 Markdown으로 읽을 수 있으며 별도 문서 서비스 접속 없이 보관된 내용을 열람할 수 있습니다. 외부 출처 링크는 별도 인터넷 접근이 필요합니다.

## 저장 구조

| 경로 | 내용 |
| --- | --- |
| `releases/<browser>/<version>/README.md` | 버전별 변경 요약 및 기능 문서 링크 |
| `features/<browser>/<feature-id>.md` | 버전 간 기능 이력 |
| `experiments/chrome/<flag-id>.md` | Chrome flag 관찰 및 검증 상태 |
| `data/events/<event-id>.json` | 구조화된 변경 사건 |
| `reports/<workstream>/README.md` | 업무별 분석 색인(중복 집계 금지) |
| `reports/YYYY-MM-DD.md` | Asia/Seoul 날짜별 의미 있는 변화 |
| `assets/` | 공개 가능한 이미지, 상대 경로로 참조 |

위 경로는 실제 데이터 발생 시 생성합니다. 빈 보고서나 가짜 샘플 결과는 만들지 않습니다.

## 운영 문서

- [브라우저별 공식 출처와 점검 주기](docs/browser-sources-and-cadence.md)
- [자동화 적용용 압축 지시문(공개본)](docs/automation-prompt.md)
- [수집 및 게시 지침](docs/collection-policy.md)
- [삼성 브라우저 PM 페르소나와 선별 규칙](docs/pm-persona-and-selection.md)
- [보고서 템플릿](templates/report.md)

## 공개 범위

공개된 제품 정보와 그에 대한 분석만 게시합니다. 사내 데이터, 비공개 의견·평가, 개인정보, 이메일 주소·메시지 ID·계정 연결 ID, 인증 정보는 저장하지 않습니다. 메일 전송 및 실행 상태는 비공개 실행 환경에서 관리합니다. 제3자 원문은 링크와 필요한 최소 인용으로 출처를 표시합니다.


### 2026-10-30 수집 추가

[최신 보고서](reports/2026-10-30.md)와 [출처별 완료·미완료 범위](docs/collection-status.md)를 참고하세요. 확장 브라우저의 최초 관찰을 추가했으나 전체 과거 이력 완료를 의미하지 않습니다.
