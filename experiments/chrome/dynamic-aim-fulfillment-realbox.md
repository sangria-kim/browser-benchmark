# Chrome dynamic-aim-fulfillment-realbox

- Flag ID: `dynamic-aim-fulfillment-realbox`
- 연결 기능: [Chrome Composebox 검색·AI Mode 라우팅 설정 실험](../../features/chrome/dynamic-aim-fulfillment.md)
- 사건: [chrome-dynamic-aim-fulfillment-source-20261112](../../data/events/chrome-dynamic-aim-fulfillment-source-20261112.json)
- 상태: source-main flag 등록 관찰. 출시·설치본 노출·실기 미확인.
- 플랫폼: Main과 Realbox는 kOsDesktop | kOsAndroid, Omnibox는 kOsDesktop이다.
- 2026-11-12 source commit: [28338c8345572c16c564bfa8d9689699187b0218](https://github.com/chromium/chromium/commit/28338c8345572c16c564bfa8d9689699187b0218)

기존 feature를 chrome://flags UI에 노출하는 등록 사건입니다. 라우팅 구현의 최초 도입이나 일반 사용자 활성화를 뜻하지 않습니다. 주 스위치와 해당 surface flag를 함께 켜야 합니다. Main/Realbox는 kOsDesktop | kOsAndroid, Omnibox는 kOsDesktop으로 등록되어 있습니다.

기존에는 raw command-line feature switches/parameters로 설정하던 조건을 chrome://flags의 7개 입력조합 선택지로 설정할 수 있게 합니다. 입력·도구·모델 조건이 AI Mode를 요구하지 않으면 일반 검색 결과로 연결한다는 소스 설명이며 실제 전송 데이터와 설치본 동작은 확인하지 않았습니다.

한국 제공·한국어 지원은 unknown이다. 소스 등록은 최초 기능 도입이나 일반 사용자 활성화를 입증하지 않는다.

OS mask 근거: kOsDesktop = Windows·macOS·Linux·ChromeOS. Main/Realbox는 Android를 추가하며 Omnibox는 네 desktop OS다. [정의](https://github.com/chromium/chromium/blob/c5715b43091a8976ccb6f69ef54bd7a3e8fb67f5/chrome/browser/about_flags.cc#L439-L440).
