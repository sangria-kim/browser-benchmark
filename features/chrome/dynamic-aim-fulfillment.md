# Chrome Composebox 검색·AI Mode 라우팅 설정 실험

- Feature ID: `chrome-dynamic-aim-fulfillment`
- 사건: `chrome-dynamic-aim-fulfillment-source-20261112`
- 업무: pc, mobile; AI 관련: true
- 현재 상태: source-main 실험 관찰, P2 / conditional. 설치본 노출·실기 동작 미확인.
- 우선순위 이유: 검색과 AI 전환의 탐색적 비교 가치가 크지만 실제 접근 조건과 설치본 노출이 확인되지 않았습니다.
- [사건 JSON](../../data/events/chrome-dynamic-aim-fulfillment-source-20261112.json) · [dynamic-aim-fulfillment](../../experiments/chrome/dynamic-aim-fulfillment.md) · [dynamic-aim-fulfillment-omnibox](../../experiments/chrome/dynamic-aim-fulfillment-omnibox.md) · [dynamic-aim-fulfillment-realbox](../../experiments/chrome/dynamic-aim-fulfillment-realbox.md)

## 확인된 변화

Composebox 질의를 일반 검색 결과 또는 AI Mode로 보내는 dynamic AIM fulfillment flag와 입력조합 7개를 등록합니다. Omnibox와 NTP Realbox를 별도로 켜며 주 스위치도 필요합니다. 기존 feature를 chrome://flags UI에 노출하는 등록 사건입니다. 라우팅 구현의 최초 도입이나 일반 사용자 활성화를 뜻하지 않습니다. 주 스위치와 해당 surface flag를 함께 켜야 합니다. Main/Realbox는 kOsDesktop | kOsAndroid, Omnibox는 kOsDesktop으로 등록되어 있습니다.

기존에는 raw command-line feature switches/parameters로 설정하던 조건을 chrome://flags의 7개 입력조합 선택지로 설정할 수 있게 합니다. 입력·도구·모델 조건이 AI Mode를 요구하지 않으면 일반 검색 결과로 연결한다는 소스 설명이며 실제 전송 데이터와 설치본 동작은 확인하지 않았습니다.

- 소스 commit 시각: 2026-11-12T02:08:02Z.
- 근거 확인일: 2026-11-13 KST. 발표일·실제 적용일은 미확인.
- 소스 등록·삭제는 단독으로 출시·철회 증거가 아니다.

## PM 비교 질문

비교 대상은 같은 플랫폼·조건의 Chrome과 삼성 브라우저다. 삼성 브라우저의 해당 기능 지원 여부는 먼저 확인하며 미지원이면 대체 흐름 또는 미지원으로 기록한다.

같은 질의와 입력 조합에서 일반 검색과 AI Mode 중 어느 경로로 연결되며, 사용자가 결과를 예측하고 선택할 수 있는가?

## 동일 조건과 재현 절차

같은 플랫폼·소스 또는 제품 버전·계정·정책·네트워크·입력 자료를 고정한다. 비교 브라우저의 해당 과제 지원 여부부터 확인하며 삼성 브라우저의 지원 여부나 내부 계획은 추정하지 않는다.

1. 동일한 테스트 빌드에서 주 스위치와 대상 surface flag의 노출을 확인한다.
2. 일반 텍스트, 이미지 1개/여러 개, 파일, 탭, Drive 첨부 조합을 동일한 질의로 반복한다.
3. 선택한 srp_input_mode와 실제 도착 화면을 기록한다.
4. 같은 플랫폼에서 비교 브라우저의 지원 여부를 먼저 확인하고 동일 과제를 비교한다.

## 지표와 완료 기준

- 일반 검색/AI Mode 라우팅 일치율
- 작업 완료까지 조작 수
- 결과 도착 시간
- 예상과 다른 경로 및 복귀 조작 수

완료 기준: 7개 srp_input_mode와 지원 surface별 결과를 재현하고 접근 불가 조건을 따로 기록한다.

아직 위 시험을 수행하지 않았다. 한국 제공·한국어 지원·기기·계정별 실제 접근 조건은 unknown이다. 소스 관찰, 설치본 노출, 동작 검증을 별도로 기록한다.

## 공식 근거

- [[Composebox] Add chrome://flags for dynamic AIM fulfillment](https://github.com/chromium/chromium/commit/28338c8345572c16c564bfa8d9689699187b0218)

플랫폼 정규화: kOsDesktop은 Windows·macOS·Linux·ChromeOS이며 Main/Realbox는 Android도 포함한다. Omnibox는 앞의 네 OS로 등록한다. 이 목록은 소스 mask이며 설치본 제공 보증이 아니다. [mask 정의](https://github.com/chromium/chromium/blob/c5715b43091a8976ccb6f69ef54bd7a3e8fb67f5/chrome/browser/about_flags.cc#L439-L440).
