# Chrome 데스크톱 메뉴 검색의 실험 진입점 추가

- Feature ID: `chrome-chro-menu-search`
- 업무: pc; AI 관련: false
- P2 우선순위 이유: 메뉴 명령을 발견하고 실행하는 한정된 탐색 과제에서 클릭 수·검색 정확도·완료 시간을 비교할 가치가 있다. 브라우저 전반의 기본 동작 변경보다 범위가 좁아 P2로 둔다.
- 현재 상태: 소스 실험 관찰, P2 / conditional. 제품 출시·설치본 노출 미확인.
- 소스 범위: 데스크톱 소스 등록. 기존 메뉴 검색 feature의 chrome://flags 진입점이며 app-menu-glow-up도 활성화해야 한다. 기본값은 비활성.

## 이력

- 2026-11-06 KST 관찰: 기존에는 명령행으로 제어하던 feature에 chro-menu-search 등록·설명·metadata를 추가했다. 메뉴 검색 자체의 최초 구현·정식 출시는 아니다.
- [사건 JSON](../../data/events/chrome-chro-menu-search-flag-20261104.json) · [상세 보고](../../reports/2026-11-06.md) · [flag 이력](../../experiments/chrome/chro-menu-search.md)
- [공식 diff](https://chromium.googlesource.com/chromium/src/+/ac186a2376a0cccda4f1e47f4946323dc0665865^!); source commit 시각 2026-11-04T00:49:40Z. 발표일·실제 적용일은 미확인.

## 비교 질문

Windows에서 동일 메뉴 명령을 계층 탐색과 검색으로 찾을 때 입력·클릭 수와 완료 시간은 어떻게 다른가? 삼성 브라우저의 동등 검색 기능 여부는 별도 확인한다.

한국 제공·한국어 지원·실제 설치본·동작 결과는 미확인/미실행이다. 삼성 브라우저 지원 여부를 추정하지 않는다.
