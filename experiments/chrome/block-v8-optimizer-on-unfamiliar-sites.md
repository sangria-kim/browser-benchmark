# block-v8-optimizer-on-unfamiliar-sites

소스 관찰과 설치본 노출·실제 동작 검증을 구분합니다.

## 2026-11-11 소스 변경

- 2026-11-11T19:03:49Z · [ad9333c403ea](https://github.com/chromium/chromium/commit/ad9333c403ea0781c8787db2ea61207cdc8671a6)
  - 익숙하지 않은 사이트의 JavaScript 최적화를 차단하는 V8 설정 옵션과 주소창 아이콘을 켜는 Desktop 실험 flag를 등록합니다.
  - 판정: watch. 사이트별 동작 이해·설정 변경·호환성 과제를 비교합니다. unfamiliar 판정 기준과 실제 제공 조건은 추가 확인이 필요합니다.

한국 제공·한국어 지원은 미확인입니다. 실기 검증은 미실행이며 실제 제품 버전·출시 여부는 확인되지 않았습니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-12.json) · [실험 색인](README.md)
