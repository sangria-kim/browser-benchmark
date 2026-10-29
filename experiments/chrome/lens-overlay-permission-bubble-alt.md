# lens-overlay-permission-bubble-alt

소스 관찰 기록입니다. 최초 도입이나 설치본 제공을 뜻하지 않습니다.

## 2026-10-30 관찰

- 종류: removal; source revision: `2e9b4bd8d8bbb10b73ebfb904c4c2d3a21263801`; commit 시각: 2026-10-29T20:20:12Z.
- 플랫폼: Windows, macOS, Linux, ChromeOS. 근거: about_flags.cc kOsDesktop.
- 관련 feature: `lens::features::kLensOverlayPermissionBubbleAlt`; 소스 기본값: previously_enabled_then_removed.
- 만료 milestone: 145 → 삭제/미확인. 만료와 삭제만으로 출시·철회를 추정하지 않습니다.
- 선별: excluded, P2, 시험 준비 unknown. Cleanup inlines previously enabled behavior; no new rollout or withdrawal established.
- 한국 제공·한국어 지원: 미확인. 설치본 노출·동작 시험: 미실행.
- 재검토: 공개 빌드 노출 또는 공식 배포·지원 조건이 확인될 때.
- [공식 diff](https://github.com/chromium/chromium/commit/2e9b4bd8d8bbb10b73ebfb904c4c2d3a21263801) · [사건 JSON](../../data/events/chrome-lens-overlay-permission-bubble-alt-removal-2e9b4bd8d8bb.json)
