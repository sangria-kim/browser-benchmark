# chro-menu-search

- Flag ID: `chro-menu-search`
- 관련 source feature: `features::kChroMenuSearch`
- 연결한 product feature ID: `chrome-chro-menu-search`. 이 관찰의 workflow identity이며 모든 flag와 기능을 1:1로 연결한다는 뜻은 아님.
- 최초 관찰: 2026-11-05T22:53:24Z; source commit: 2026-11-04T00:49:40Z
- revision: `ac186a2376a0cccda4f1e47f4946323dc0665865`
- 플랫폼: Windows, macOS, Linux, ChromeOS (소스 조건, 배포 증거 아님)
- 활성화 진입점: `chrome://flags/#chro-menu-search`. 데스크톱 소스 등록. 기존 메뉴 검색 feature의 chrome://flags 진입점이며 app-menu-glow-up도 활성화해야 한다. 기본값은 비활성.
- 등록 시 expiry milestone: 165. 만료값은 출시·철회 시점이 아님.

## 2026-11-06 관찰

기존에는 명령행으로 제어하던 feature에 chro-menu-search 등록·설명·metadata를 추가했다. 메뉴 검색 자체의 최초 구현·정식 출시는 아니다.

[공식 diff](https://chromium.googlesource.com/chromium/src/+/ac186a2376a0cccda4f1e47f4946323dc0665865^!) · [월별 전체 이력](monthly/2026-11-source-index-2026-11-06.json) · [제품 기능 이력](../../features/chrome/chro-menu-search.md) · [선정 사건](../../data/events/chrome-chro-menu-search-flag-20261104.json)

검증: 3개 현재 파일의 전체 증분 diff를 순서대로 적용하여 공식 종료 snapshot과 일치 확인. 설치본 노출·한국 제공·한국어 지원·직접 동작 검증은 미확인/미실행.
