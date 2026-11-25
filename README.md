# Browser Benchmark

지정된 공식 출처에서 브라우저별 업데이트를 수집하고, 실제 기능 변화를 분류해 저장합니다. 대상은 Chrome, Edge, Firefox, Safari, Brave, Whale, Opera, Vivaldi입니다. 수집할 사이트와 채널은 [출처 설정](config/sources.yml)에서 확인할 수 있습니다.

## 수집 결과

- [기능 목록](data/catalog/features/catalog.json)에서 브라우저와 기능 이름을 찾습니다. 각 기능의 `source_item_ids`는 [공식 출처 근거](data/source-items/)로 연결됩니다.
- 수집 에이전트는 원문을 읽고 기능의 추가·변경·지원 확대·제거를 식별합니다. 보안 패치, 일반 오류 수정, 배포 공지, 홍보 문구, 근거가 불명확한 항목은 새 공개 자료에서 제외합니다. 적용 기준과 저장 명령은 [수집 기준](docs/collection-policy.md)과 [실행 안내](pipeline/OPERATIONS.md)에 있습니다.
- 사내 반입 준비, 패키징, 동기화, 사내 분석과 배포는 소비 환경에서 담당합니다. 이 저장소의 수집 작업은 기능과 출처 근거를 저장하면 끝납니다.

## 공개 데이터 재사용

[공개 데이터 allowlist](config/public-dataset-allowlist.json)는 기능 목록과 공식 근거의 읽기 범위를 정의합니다. 소비자는 `main`의 커밋 SHA를 한 번 확인하고, 목록과 모든 데이터를 같은 SHA에서 읽습니다. 다음 예시는 저장소에서 Git과 jq로 첫 기능의 ID와 근거 ID를 조회합니다.

```sh
git fetch origin main
sha=$(git rev-parse origin/main)
catalog=$(git show "${sha}:config/public-dataset-allowlist.json" | jq -er '.catalog.path')
git show "${sha}:$catalog" | jq '.[0] | {feature_id, title, source_item_ids}'
```

- 기능의 식별자는 `feature_id`입니다. 근거 파일 패턴은 저장소 루트 기준이고, 각 `*`는 한 경로 구성요소 안에서만 일치합니다. Edge 정책의 분할 파일도 이 패턴에 포함됩니다. 각 파일에서 기능의 `source_item_ids`에 들어 있는 `source_item_id`만 읽습니다. 한 근거를 여러 기능이 참조하면 각 연결을 유지합니다.
- 현재 근거는 기능의 `source_revision_ids[출처 ID]`에서 마지막 ID를 골라 출처의 `revisions`에서 같은 `revision_id`를 찾아 읽습니다. 인용문은 기능의 `source_revision_excerpts[리비전 ID]`를 우선하고, 생략된 경우 해당 리비전의 `evidence.excerpt`를 씁니다. 과거 연결에 리비전 ID 목록이 없으면 고정한 커밋의 출처 항목에서 `evidence`를 읽고 ‘커밋 시점 근거’로 구분합니다.
- 소비자는 모든 출처 ID와 지정된 리비전 ID가 연결되는지 확인하고, 읽기와 저장이 성공하면 사용한 SHA를 기록합니다. 반입 주기와 저장 형식은 소비 환경에서 관리합니다.

### 일일 수집 상태

선택 경로 `data/daily-status/YYYY-MM-DD.json`은 수집 결과만 전달합니다. 기능 목록이나 보고서가 아닙니다. 소비자는 오늘 한국 날짜의 파일과 기능·근거를 같은 `main` 커밋에서 읽습니다.

새 결과의 마감은 한국시간 07:00입니다. 기존 08:00 결과도 같은 형식으로 읽습니다.

`{"date":"2026-11-24","cutoff":"2026-11-24T07:00:00+09:00","status":"complete","collected_feature_count":1,"change_count":0}`

- `collected_feature_count`: 분류 후 채택한 고유 기능 수입니다. 공식 근거만 보강한 기능도 포함합니다. 제외한 후보나 기존 전체 카탈로그는 세지 않습니다.
- `complete` + `change_count: 0`: 오늘 업데이트 없음. 일일 대상 출처의 수집과 분류·검증이 끝났습니다. Brave, Vivaldi, Opera는 주간 대조와 수동 수집에서 확인합니다.
- `complete` + 양의 `change_count`: 확인된 실질 변경이 있는 기능 수입니다. 여러 근거가 한 기능을 설명하면 한 번만 셉니다.
- `incomplete` + 두 건수 모두 `null`: 수집 또는 분류·검증 미완료입니다. 변경 없음으로 표시하지 않습니다.
- 파일 없음, 아직 미병합 또는 미동기화: 오늘 결과 미반영입니다. 이전 날짜의 결과를 오늘의 결과로 쓰지 않습니다.

Allowlist의 `daily_status`는 기능 근거와 별개입니다. 파일명과 날짜·마감·상태·건수 조합이 맞는 파일만 읽으세요.

브라우저별 중간 결과를 읽는 소비자는 동일한 커밋의 `data/browser-status/<mode>/<UTC 시각>.json`을 함께 읽습니다. `scope.expected`에는 필수 출처가, `browsers`에는 브라우저별 완료 상태와 두 건수가 들어 있습니다. 일일 전체가 미완료여도 개별 완료 브라우저의 기능과 근거는 사용할 수 있습니다. [저장과 재시도 절차](pipeline/OPERATIONS.md#브라우저별-저장과-재시도)

## 기존 자료

이전에 저장한 [기능 문서](features/README.md), [릴리스](releases/README.md), [기능 사건](data/events/README.md), [Chrome 실험](experiments/chrome/README.md), [일일 리포트](reports/generated/README.md)와 [공개 대시보드](https://sangria-kim.github.io/browser-benchmark/)를 열람할 수 있습니다. 이전 수집분에는 일반 수정과 제외 항목도 들어 있습니다. [폴더 구조](docs/data-layout.md)

변경 사항은 `work/browser-benchmark`에서 검증하고 `main` 대상 PR로 제출합니다. 저장소 소유자가 검토하고 병합합니다. [작업 규칙](AGENTS.md)
