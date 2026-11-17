# Browser Benchmark

Chrome·Edge·Firefox·Brave·Whale·Opera·Vivaldi·Safari의 공개 기능 변화와 Chromium 소스 실험을 정리합니다. Windows와 Android를 중심으로 기능 설명, 공식 출처, 제품 조건, 비교 과제를 제공합니다.

## 대시보드와 리포트

- [공개 대시보드](https://sangria-kim.github.io/browser-benchmark/)에서 현재 선정 기능, Chrome 실험, 전체 수집 자료, 판정 이력과 일일 리포트를 볼 수 있습니다. [로컬 실행 및 배포 안내](dashboard/README.md)를 참고하세요.
- [자동 생성 일일 리포트](reports/generated/README.md)는 선정 변화, 과거 자료 보강, 사실 정정을 날짜와 리포트 버전별로 보여 줍니다. [기존 수동 분석](reports/README.md)과 [PC](reports/pc/README.md)·[Mobile](reports/mobile/README.md)·[AI](reports/ai/README.md) 색인도 제공합니다.
- [브라우저별 릴리스](releases/README.md), [기능별 이력](features/README.md), [기능 사건](data/events/README.md), [기존 Chrome flag 문서](experiments/chrome/README.md)에서 원래 자료를 볼 수 있습니다.

## 수집과 선정 범위

브라우저 기능은 **2026년 1월 1일 00:00 한국시간**부터 각 출처의 수집 마감까지 공식 발표·변경 근거가 있는 항목을 조사합니다. 시간대가 있는 게시 시각은 그대로 판정에 사용하며, 날짜만 있는 자료는 원문에 적힌 날짜를 사용합니다. 기간 이전 자료는 이력으로 보존합니다. 날짜를 확인할 수 없는 항목은 기간 내 변화로 집계하지 않습니다. [공식 출처 목록](docs/browser-sources-and-cadence.md)

Chromium은 연초 직전과 수집 시점의 고정 커밋을 비교합니다. 현재 존재하는 UI flag, base feature, command-line switch 중 추가됐거나 의미·기본값·조건이 달라진 정의를 찾습니다. 이 비교 범위에는 중간에만 존재했던 정의나 삭제된 정의가 포함되지 않습니다. 소스 등록, 실제 출시, 설치본 노출, 직접 동작 확인은 각각 구분합니다. [수집 범위 설정](config/chrome-source-scope.yml)

[PM 선정 규칙](docs/pm-persona-and-selection.md)은 사용자 영향, 실질적 변화, 비교 가치, 검증 가능성, 출시 조건을 평가합니다. 보안 수정, 일반 수정, 미해석 항목과 선정에서 제외된 항목도 원천 목록에서 볼 수 있습니다. 일일 리포트에는 수집·평가가 완료됐는지 표시합니다. [기능 분석 템플릿](templates/report.md)

## 데이터와 사내 반입

원천 근거, 기능·실험 사실, 변경 사건, PM 판정, 현재 선정, 리포트를 별도로 저장합니다. 기존 문서 경로와 사건 ID도 유지합니다.

| 경로 | 내용 |
| --- | --- |
| [data/source-items/](data/source-items/) | 수집 항목과 공식 출처 근거 |
| [data/catalog/](data/catalog/) | 기능·실험 카탈로그 |
| [data/events/](data/events/), [data/experiment-events/](data/experiment-events/) | 기능·실험 변경 사건 |
| [data/assessments/](data/assessments/) | PM 판정과 판정 이력 |
| [현재 선정 기능](data/selected/features/current.json), [현재 선정 실험](data/selected/flags/current.json) | 현재 선정과 선정 변화 |
| [data/reports/](data/reports/) | 현재 리포트와 이전 버전 |

새 데이터 내보내기는 계약 `1.2`를 사용합니다. 사내 반입 시 소유자가 병합한 `main`의 커밋 SHA를 고정하고, 허용 목록에 있는 자료와 문서만 가져옵니다. 반입한 SHA를 사내 환경에 기록합니다. [사내 반입 안내](docs/internal-import-instructions.md) · [내보내기 허용 목록](config/export-allowlist.json) · [데이터 계약](docs/dataset-contract.md)

## 공개 경계

공개 자료에는 제품 사실, 공식 URL, 확인에 필요한 최소 근거와 정정 이력을 둡니다. 원문 캐시, 운영 로그, 인증 정보, 개인 식별자와 사내 분석은 비공개 환경에 둡니다. [공개 자료 원칙](docs/collection-policy.md)

## 작업 및 반영 규칙

포도와 Codex를 포함한 모든 agent는 `work/browser-benchmark`에서 작업합니다. 검증 후 이 브랜치에 push하고 `main` 대상 PR을 만듭니다. `main` 직접 push와 agent의 PR merge는 금지합니다. 저장소 소유자가 PR을 검토하고 merge합니다. 자세한 절차는 [AGENTS.md](AGENTS.md)를 따릅니다.

| 가져올 브랜치 | 반영 시점 | 의미 |
| --- | --- | --- |
| `work/browser-benchmark` | agent가 검증 후 push한 시점 | 소유자 검토 전 후보 자료 |
| `main` | 소유자가 PR을 merge한 시점 | 소유자가 검토한 자료 |

자료를 가져오는 환경은 기준 브랜치와 반영한 커밋 SHA를 기록합니다.
