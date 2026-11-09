# 공개 기능 자료 구조

## 자료 간 관계

```text
공개 공식 출처
  ├─ releases/<browser>/<version>/  버전별 기능과 근거
  └─ experiments/chrome/           소스 revision과 flag 변경
                  ↓
       data/events/<event-id>.json  변화 한 건의 사실·조건·판정
                  ↓ feature_id
       features/<browser>/*.md     같은 기능의 여러 변화 이력
                  ↓ event_id
       reports/YYYY-MM-DD.md       기능 분석과 제안 벤치마크
                  ↓
       reports/pc · mobile · ai     같은 분석을 연결하는 업무별 색인
```

- [릴리스 색인](../releases/README.md)에서 브라우저와 버전으로 찾습니다.
- [기능 색인](../features/README.md)에서 같은 기능의 변경 이력을 찾습니다.
- [사건 색인](../data/events/README.md)에서 ID와 판정 상태로 찾습니다.
- [날짜별 분석](../reports/README.md)은 사용자 영향, 비교 질문, 시험 조건을 설명합니다.
- [Chrome 소스 실험](../experiments/chrome/README.md)은 제품 출시와 분리해서 읽습니다.

화살표는 자료의 연결 관계입니다. 모든 릴리스 항목이 선정되거나 모든 과거 보고서가 구조화 사건으로 변환됐다는 뜻은 아닙니다. 기존 보고서의 사실·근거·정정은 원래 경로에 보존합니다.

## 식별자와 중복

`feature_id`는 같은 기능을 묶는 키입니다. 문서 파일명만으로 기능 ID를 추정하지 말고 문서와 사건의 값을 읽으세요. `event_id`는 특정 변경 사건 한 건의 키입니다. 새 기능, Beta에서 Stable로의 확대, 기본값 변경, 수정, 종료 예고와 실제 종료는 서로 다른 사건일 수 있습니다.

같은 사건이 PC와 AI 색인에 함께 있어도 한 번만 셉니다. 동일한 공식 문서의 새 확인일이나 편집일만으로 새 출시 사건을 만들지 않습니다. 기존 사건의 사실 정정은 원래 ID와 이전 판단 근거를 보존합니다.

## 사실과 해석

- `announced_at`: 공식 발표일. 문서 편집일이나 확인일과 다를 수 있습니다.
- `effective_at`: 근거로 확인한 적용일. 계획·예고만 있으면 비워 둡니다.
- `observed_at`: 해당 근거를 확인한 시점. 제품 출시일이 아닙니다.
- `source_revision`, URL, section, 내용 hash: 공개 근거를 식별합니다.
- `scope`: 버전·채널·플랫폼·지역·언어·계정 등 제품 조건입니다.
- `verification_status`: 공식 문서, 소스, 설치본, 실제 동작의 증거 수준을 구분합니다.
- `selection_status`: selected / watch / pending_verification / excluded입니다.
- `priority`: P1 / P2 / null입니다. 심각도나 출시 보증이 아닙니다.
- `benchmark_readiness`: ready / conditional / unknown입니다. 시험 완료 여부와 다릅니다.

근거가 부족한 값은 null 또는 unknown으로 남깁니다. 예고·소스 등록·릴리스 노트 수록을 모든 사용자에게 활성화된 기능으로 바꾸어 읽지 마세요. 자세한 필드는 [공개 자료 원칙](collection-policy.md), 판정 기준은 [PM 분석 기준](pm-persona-and-selection.md)을 따릅니다.

## 공개 자료와 비공개 기록

이 저장소에는 기능 사실, 공개 근거, 제품 조건, 기능 사실 정정, 분석과 시험 설계를 둡니다. 조사 범위·오류·재개 지점·작업 결과·발송 상태는 비공개 날짜별 기록에 둡니다. 비공개 기록 주소와 원문 첨부는 이 저장소에 넣지 않습니다.

기존 경로와 ID는 유지합니다. 과거 Git 이력은 재작성하지 않습니다. 자료를 가져올 때의 브랜치와 승인 의미는 [작업 규칙](../AGENTS.md#consumers)을 참고하세요.
