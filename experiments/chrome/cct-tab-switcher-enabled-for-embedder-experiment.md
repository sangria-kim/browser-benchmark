# cct-tab-switcher-enabled-for-embedder-experiment

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-08-13 | added | kOsAndroid | [1bdec6a5c044](https://github.com/chromium/chromium/commit/1bdec6a5c044e2aae9df939f30b9c8b086d39cf4) |

[전체 목록](README.md)

## 2026-11-09 소스 변경

- 2026-11-09T20:44:07Z · [2bf5e7bda074](https://github.com/chromium/chromium/commit/2bf5e7bda0748ae80c4d0f6a300599a9ae289512)
  - Android Custom Tabs 실험 flag 두 개의 이름과 설명을 바꿉니다. Chrome 주도 실험은 tabbed-cct-if-allowed-by-embedder, embedder 주도 실험은 tabbed-cct-if-enabled-by-embedder로 이어집니다. 이름 변경을 새 사용자 기능 도입으로 세지 않습니다.
  - 판정: excluded · 호출 앱 조건 또는 설치본 동작이 실질적으로 바뀐 공식 근거를 확인할 때 재검토합니다.

플랫폼 근거: Android. 소스 조건이며 실제 설치본 지원을 보장하지 않습니다. 한국 제공·한국어 지원·최소 버전은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-10.json) · [실험 색인](README.md)
