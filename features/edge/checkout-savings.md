# 결제 화면의 Checkout Savings 쿠폰 제안

- Feature ID: `edge-checkout-savings`
- Windows·macOS, 정확 버전·채널 미공개. 공식 문헌 분석, 실기 미실행.
- 발표: 2026-11-09. 개인별 활성화일 미확인.

## 변화와 이전 기능
결제단계에서 백그라운드로 쿠폰을 찾고 사용 가능한 쿠폰이 있으면 표시한다. 기존 가격비교·가격추적·캐시백과 구분하며 자동 주문이나 결제 기능으로 설명하지 않는다.

2020-11-19 공식 글의 결제시점 쿠폰 제안과 겹친다. 새로운 이름과 문구만으로 신규 사용자 기능으로 세지 않는다.

## 판정과 검증
pending_verification / 우선순위 미부여: 11/9 새 이름의 공식 발표는 확인했으나 2020년 공식 글에도 결제 시 쿠폰 제안·자동 입력이 존재한다. 새 동작·대체 관계·출시 단계의 실질적 차이를 입증하지 못했다.

삼성 브라우저에서 결제 전에 쿠폰을 찾고 적용하는 단계와 유효 조건을 확인하는 방법은 무엇이며, 제안을 끄거나 무시할 수 있는가? 지원 여부는 별도 확인한다.

한국 제공·한국어 지원은 미확인. 비교는 Copilot 시장, Checkout Savings는 en-US 제한. 사이트별로 다르며 자동 결제 기능이 아니다.

[사건과 벤치마크 과제](../../data/events/edge-checkout-savings-rollout-20261109.json)

## 공식 근거
- https://blogs.windows.com/msedgedev/2026/11/09/shop-faster-and-save-money-with-built-in-tools-in-microsoft-edge/
- https://blogs.windows.com/windowsexperience/2020/11/19/finish-up-that-holiday-shopping-with-new-features-from-microsoft-edge-and-bing/
- https://explore.microsoft.com/ko-kr/edge/features/shopping?form=MT0160
