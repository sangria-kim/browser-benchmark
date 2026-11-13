# Chrome FedCM 신규 계정 동의를 modal로 이동하는 실험

- Feature ID: `chrome-fedcm-idp-links` · Event ID: `chrome-fedcm-passive-signup-modal-source-20261113`
- Chrome source-main · Windows, macOS, Linux, ChromeOS · P1 · conditional
- 소스 변경: 2026-11-13T21:53:00Z · 근거 검증: 2026-11-13T22:57:51Z
- 공식 발표일·제품 효력일·버전: 미확인. 설치본 노출·실기 시험: 미실행.

## 변경 전후와 사용자 영향

FedCM passive 로그인에서 처음 정보를 공유하는 계정의 동의 화면을 bubble에서 modal로 옮겨 IdP의 계정관리·개인정보처리방침·약관 링크를 보여줍니다. 기존 재방문 계정은 원래 흐름을 유지합니다.

단일 IdP·단일 신규 계정은 1회에서 2회 선택으로 바뀝니다. 여러 계정은 2회 선택을 유지하되 두 번째 동의가 modal에서 이뤄집니다. 같은 날 후속 commit은 별도 multiple-IdP flag가 켜진 경우 복수 IdP에도 적용합니다. 두 flag 조건이 충족되지 않은 복수 IdP 요청은 bubble에서 동의합니다. 2026-11-11의 기존 사건은 링크 출처를 well-known으로 바로잡은 설명 변경이었다. 이번은 passive 신규 계정의 실제 dialog 전환 코드와 복수 IdP 조건 변경이므로 기존 링크 기능의 최초 도입이 아니라 동작 변경이다.

## PM 선별과 비교 질문

인증 동의 단계의 링크 발견성·공유 정보 이해·되돌리기·추가 조작 비용을 같은 과제로 비교할 수 있습니다. 출시가 아니라 소스 실험으로 선정합니다.

우선순위 이유: 인증 동의와 정보 공유 안내의 핵심 과제가 달라지므로 우선 비교합니다.

삼성 브라우저와 같은 FedCM 테스트 사이트·계정·플랫폼 조건에서, 새 계정의 공유 정보와 IdP 링크를 확인하고 동의를 취소하거나 계정을 바꾸는 흐름은 어떻게 다른가?

## 벤치마크

1. 테스트용 RP/IdP와 합성 계정을 준비하고 공유 권한이 필요한 새 계정·재방문 계정을 나눕니다.
2. 같은 빌드·OS에서 flags off, IdP links on, 두 flags on 조건을 구분합니다.
3. 단일 IdP의 한 계정/여러 계정과 복수 IdP에서 링크 확인, Continue, Back, 취소, 오류 후 재시도를 반복합니다.
4. 삼성 브라우저의 FedCM 및 해당 조건 지원 여부부터 확인한 뒤 같은 과제로 비교합니다.

지표: 가입 완료 선택 수와 시간 · 공유 정보·IdP 링크 노출 여부 · Back/취소 후 계정 선택 및 원문 복귀 · 오류·재시도 후 dialog 종류

완료 기준: 각 지원 조건을 3회 반복하고 새/재방문 계정 및 단일/복수 IdP 결과를 분리합니다. 소스 예상과 실제 설치본 결과 차이를 명시합니다.

## 제공 조건과 미확인 사항

- region: unknown
- language: unknown
- account: unknown
- korea_availability: unknown
- korean_language_support: unknown
- device_test: not_run
- installed_build_exposure: unknown
- default: kFedCmIdpLinks is FEATURE_DISABLED_BY_DEFAULT; not modified by these commits
- single_idp_required: kFedCmIdpLinks enabled
- multiple_idp_required: kFedCmIdpLinks AND kFedCmActiveModeMultipleIdentityProviders enabled
- returning_accounts: Existing flow unchanged
- telemetry_caveat: Source notes passive flows through modal still record active-mode metrics; do not infer usage from those metrics without adjustment
- platform_evidence: kOsDesktop registration mask expands to listed OS; no installed OS tested

한국 제공·한국어 지원은 미확인입니다. 지역·계정·제품 배포 여부를 소스 등록에서 추정하지 않습니다. 소스 변경, 설치본 노출, 직접 동작 확인은 별개입니다. 재검토: 공식 시험 빌드와 동일 조건에서 노출·동작을 확인하거나 공식 배포 범위가 확인되면 갱신합니다.

## 공식 근거

- [[FedCM] Request passive mode sign-up permission in the modal dialog](https://github.com/chromium/chromium/commit/199a8e77c6b2f9e66f4fc00c44624706c118a16f)
- [[FedCM] Use the modal for passive mode sign-up with multiple IdPs](https://github.com/chromium/chromium/commit/6562990bab15390e8ccca4a00f3ba421e46929c4)
- [기존 IdP 링크 설명 변경 (2026-11-11, 신규 UI 출시 아님)](https://github.com/chromium/chromium/commit/542d7914a86f0915025d40e699fa2de876d36e7d)

[구조화 사건](../../data/events/chrome-fedcm-passive-signup-modal-source-20261113.json) · 판정 기준 pm-selection-v2
