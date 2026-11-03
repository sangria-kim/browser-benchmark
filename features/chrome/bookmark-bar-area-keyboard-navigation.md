# 북마크바 구역별 키보드 탐색 실험

- browser: chrome
- canonical feature key: `bookmark-bar-area-keyboard-navigation`
- feature_id: `chrome-bookmark-bar-area-keyboard-navigation`

## 이력

- 2026-11-03 20:47:29 UTC: [공식 소스 commit](https://github.com/chromium/chromium/commit/0a00fca6c891b90ff58b40e1d82c023212c065ea)이 신규 flag·기본 비활성 feature·키보드 focus 처리를 추가했습니다. 제품 출시일은 미확인입니다.
- 2026-11-04 KST: source-only 실험 후보로 selected / P2 판정. Windows·Linux·ChromeOS 소스 mask, 설치본 노출·한국 제공·한국어 지원은 미확인입니다.
- [사건](../../data/events/chrome-source-0a00fca6c891b90ff58b40e1d82c023212c065ea.json) · [분석과 벤치마크 후보](../../reports/2026-11-04.md) · [flag 기록](../../experiments/chrome/bookmark-bar-area-keyboard-navigation.md).

구역별 첫 표시 버튼에만 Tab이 정지하고 좌우 키로 구역 내부 버튼을 순환하는 설계입니다. 조건을 갖춘 설치본의 비활성/활성 비교가 필요하며 실제 시험은 미실행입니다.
