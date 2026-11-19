# Browser Benchmark

지정된 공식 출처에서 브라우저별 업데이트를 수집하고, 실제 기능 변화를 분류해 저장합니다. 대상은 Chrome, Edge, Firefox, Safari, Brave, Whale, Opera, Vivaldi입니다. 수집할 사이트와 채널은 [출처 설정](config/sources.yml)에서 확인할 수 있습니다.

## 수집 결과

- [기능 목록](data/catalog/features/catalog.json)에서 브라우저와 기능 이름을 찾습니다. 각 기능의 `source_item_ids`는 [공식 출처 근거](data/source-items/)로 연결됩니다.
- 수집 에이전트는 원문을 읽고 기능의 추가·변경·지원 확대·제거를 식별합니다. 보안 패치, 일반 오류 수정, 배포 공지, 홍보 문구, 근거가 불명확한 항목은 새 공개 자료에서 제외합니다. 적용 기준과 저장 명령은 [수집 기준](docs/collection-policy.md)과 [실행 안내](pipeline/OPERATIONS.md)에 있습니다.
- 사내 반입 준비, 패키징, 동기화, 사내 분석과 배포는 소비 환경에서 담당합니다. 이 저장소의 수집 작업은 기능과 출처 근거를 저장하면 끝납니다.

## 기존 자료

이전에 저장한 [기능 문서](features/README.md), [릴리스](releases/README.md), [기능 사건](data/events/README.md), [Chrome 실험](experiments/chrome/README.md), [일일 리포트](reports/generated/README.md)와 [공개 대시보드](https://sangria-kim.github.io/browser-benchmark/)를 열람할 수 있습니다. 이전 수집분에는 일반 수정과 제외 항목도 들어 있습니다. [폴더 구조](docs/data-layout.md)

변경 사항은 `work/browser-benchmark`에서 검증하고 `main` 대상 PR로 제출합니다. 저장소 소유자가 검토하고 병합합니다. [작업 규칙](AGENTS.md)
