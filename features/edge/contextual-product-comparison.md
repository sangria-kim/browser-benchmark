# 유사 상품 탭에서 Copilot 비교를 제안

- Feature ID: `edge-contextual-product-comparison`
- Windows·macOS, 정확 버전·채널 미공개. 공식 문헌 분석, 실기 미실행.
- 발표: 2026-11-09. 개인별 활성화일 미확인.

## 변화와 이전 기능
사용자가 먼저 Copilot에 탭 비교를 질문하는 기존 흐름에서, 비슷한 상품 탭을 감지해 비교를 제안하는 흐름으로 확장. 비교 선택 후 페이지 전체를 읽고 요약하며 후속 질문에 맥락을 사용한다.

2026-05-13 공식 글은 사용자가 Copilot에 질문해 여러 탭 정보를 비교하는 흐름을 설명한다. 2026-11-09 글은 유사 상품 탭을 인식해 비교를 먼저 제안한다고 명시한다. 다중 탭 추론·상품 비교 자체의 최초 도입이 아니다.

## 판정과 검증
selected / P2: 기존 질문형 여러 탭 비교와 달리 유사 상품 탐색 맥락에서 비교 진입을 제안한다. 진입 조작·동의·비교 정확도 검토 과제가 명확하다.

삼성 브라우저에서 여러 상품 탭을 비교할 때 비교 대상을 어떻게 선택하며, 페이지 읽기 동의·결과 확인·제안 끄기를 어디서 하는가? 지원 여부는 별도 확인한다.

한국 제공·한국어 지원은 미확인. 비교는 Copilot 시장, Checkout Savings는 en-US 제한. 사이트별로 다르며 자동 결제 기능이 아니다.

[사건과 벤치마크 과제](../../data/events/edge-contextual-product-comparison-rollout-20261109.json)

## 공식 근거
- https://blogs.windows.com/msedgedev/2026/11/09/shop-faster-and-save-money-with-built-in-tools-in-microsoft-edge/
- https://blogs.windows.com/msedgedev/2026/05/13/new-updates-to-edge-across-desktop-and-mobile/
- https://explore.microsoft.com/ko-kr/edge/features/shopping?form=MT0160
