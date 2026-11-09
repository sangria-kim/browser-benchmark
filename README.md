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
