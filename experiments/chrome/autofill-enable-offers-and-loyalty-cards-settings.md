# autofill-enable-offers-and-loyalty-cards-settings

소스 관찰 기록입니다. 최초 도입이나 설치본 제공을 뜻하지 않습니다.

## 2026-10-30 관찰

- 종류: registration; source revision: `701fc033a82d424cd2f9741e4dcd3c1e1559847c`; commit 시각: 2026-10-29T18:43:14Z.
- 플랫폼: Windows, macOS, Linux, ChromeOS. 근거: about_flags.cc kOsDesktop.
- 관련 feature: `autofill::features::kAutofillEnableOffersAndLoyaltyCardsSettings`; 소스 기본값: disabled.
- 만료 milestone: 없음/미확인 → 170. 만료와 삭제만으로 출시·철회를 추정하지 않습니다.
- 선별: watch, P2, 시험 준비 conditional. Gate proposes a separate Offers and loyalty cards settings leaf/toggle instead of Payments; this commit contains flag definitions rather than completed settings UI.
- 한국 제공·한국어 지원: 미확인. 설치본 노출·동작 시험: 미실행.
- 재검토: 공개 빌드 노출 또는 공식 배포·지원 조건이 확인될 때.
- [공식 diff](https://github.com/chromium/chromium/commit/701fc033a82d424cd2f9741e4dcd3c1e1559847c) · [사건 JSON](../../data/events/chrome-autofill-enable-offers-and-loyalty-cards-settings-registration-701fc033a82d.json)
