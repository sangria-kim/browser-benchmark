# menu-simplification

- 기존 flag. 2026-11-10 만료 연장은 최초 도입이 아니다. [기존 이력](monthly/2026-11-source-index-2026-11-11.json).
- 2026-11-13 22:36:33 UTC: `glic section above save` 옵션을 추가했다. `MenuSimplificationGlicSearchAboveSaveAndPrint=true`이면 텍스트 미선택·비편집 페이지 메뉴의 Gemini·검색 구역을 저장·인쇄 위로 옮긴다.
- feature: `kMenuSimplification`. 기능·매개변수 기본값은 비활성화다.
- 플랫폼 근거: `kOsDesktop`. 설치본·동작·제품 버전·한국 제공은 미확인.
- 공식 commit에는 메뉴 구분선 단위시험 변경이 있다. 이 조사에서 그 시험을 실행한 것은 아니다.

[공식 diff](https://github.com/chromium/chromium/commit/547fe3d4765d6d9821019bdb0101fbeea01a0452) · [사건](../../data/events/chrome-context-menu-gemini-search-order-source-20261113.json)
