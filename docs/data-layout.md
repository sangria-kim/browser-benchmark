# 공개 자료 구조

| 경로 | 용도 |
| --- | --- |
| [config/sources.yml](../config/sources.yml) | 브라우저별 공식 출처와 수집 범위 |
| [data/catalog/features/catalog.json](../data/catalog/features/catalog.json) | 브라우저별 기능 ID, 이름, 출처 항목 ID |
| [data/source-items/](../data/source-items/) | 새로 분류한 기능의 공식 근거와 기존 원천 이력 |

기능 키는 브라우저별로 관리합니다. 같은 기능을 다시 확인하면 같은 키에 출처를 연결합니다. 출처 항목에는 버전, 채널, 플랫폼, 근거 URL, 발표일과 관찰 시각이 있습니다. Edge 정책 자료는 기존 256개 파일에 항목 ID 기준으로 나누어 저장합니다.

기능의 `source_revision_ids`에는 출처 항목별로 확인한 리비전 ID를 오래된 순서로 저장합니다. 대시보드는 각 기능에서 마지막으로 확인한 리비전의 근거를 표시합니다. `source_revision_excerpts`는 기능별로 확인한 인용문을 리비전 ID에 연결합니다. 인용문을 따로 지정하지 않은 리비전은 저장된 출처 발췌문을 표시합니다. `source_revision_ids`가 없는 기존 연결은 출처를 갱신할 때 직전 표시 버전을 기록합니다.

기존 실험·사건·판정·선정 목록과 리포트는 이전 경로에서 조회할 수 있습니다. 과거 레코드의 형식은 [자료 계약](dataset-contract.md)에 있습니다. 신규 수집은 [수집 기준](collection-policy.md)을 따릅니다.
