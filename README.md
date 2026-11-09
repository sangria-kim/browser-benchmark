# Browser Benchmark

Chrome·Edge·Firefox·Brave·Whale·Opera·Vivaldi의 공개 브라우저 기능, 동작 변경 및 소스 실험을 정리합니다. Windows와 Android를 중심으로 기능 설명·공식 출처·버전·제품 조건·비교 과제를 제공합니다.

## 기능 자료

- [브라우저별 릴리스](releases/README.md)
- [날짜별 기능 분석](reports/README.md)
- [PC](reports/pc/README.md) · [Mobile](reports/mobile/README.md) · [AI](reports/ai/README.md)
- [Chrome 실험 기능](experiments/chrome/README.md)
- [공식 출처](docs/browser-sources-and-cadence.md)

## 해석 기준

공식 발표, 소스 등록, 설치본 노출, 직접 동작 확인은 서로 다른 증거입니다. flag 추가·삭제만으로 출시·철회를 단정하지 않습니다. Stable/Beta/실험/예고와 지역·언어·계정·기기·구독·단계적 배포 조건을 각각 확인하세요. 문헌 기반 자료와 제안된 벤치마크는 실측 결과가 아닙니다.

P1은 사용자 과제에 큰 영향을 주어 우선 비교할 변화, P2는 조건을 확인하며 비교할 변화입니다. 버그 심각도나 출시 보증이 아닙니다. [분석 기준](docs/pm-persona-and-selection.md) · [공개 자료 원칙](docs/collection-policy.md) · [기능 분석 템플릿](templates/report.md)

## 저장 구조

- releases/: 브라우저·버전별 기능 항목과 공식 출처
- features/: 기능별 변경 이력
- experiments/chrome/: flag별 소스 변경과 revision
- data/events/: 기능 사건, 제품 범위와 증거
- reports/: 날짜별 기능 분석과 업무별 색인

## 공개 경계

이 저장소에는 브라우저 기능 내용과 이를 해석하는 근거만 둡니다. 조사 진행도, 확인하지 못한 자료 목록, 실행·실패·발송·게시 기록 및 개인 식별자는 공개하지 않습니다. 운영 원문과 정정 이력은 비공개 Notion의 일별 기록으로 분리합니다. 기능 자체의 제품 제약·근거 수준·사실 정정은 공개 기능 자료에 유지합니다.

## 작업 및 반영 규칙

포도와 Codex를 포함한 모든 agent는 `work/browser-benchmark`에서 작업합니다. 검증 후 이 브랜치에 push하고 `main` 대상 PR을 만듭니다. `main` 직접 push와 agent의 PR merge는 금지합니다. 저장소 소유자가 PR을 검토하고 merge합니다. 자세한 절차는 [AGENTS.md](AGENTS.md)를 따릅니다.

| 가져올 브랜치 | 반영 시점 | 의미 |
| --- | --- | --- |
| `work/browser-benchmark` | agent가 검증 후 push한 시점 | 소유자 검토 전 후보 자료 |
| `main` | 소유자가 PR을 merge한 시점 | 소유자가 검토한 자료 |

자료를 가져오는 환경은 기준 브랜치를 명시하고 반영한 commit SHA를 기록합니다. 이 문서 변경은 외부 스케줄러의 설정을 변경하지 않습니다.
