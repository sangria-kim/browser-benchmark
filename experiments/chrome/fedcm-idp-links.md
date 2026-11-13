# fedcm-idp-links

소스 관찰과 설치본 노출·실제 동작 검증을 구분합니다.

## 2026-11-11 소스 변경

- 2026-11-11T18:34:35Z · [542d7914a86f](https://github.com/chromium/chromium/commit/542d7914a86f0915025d40e699fa2de876d36e7d)
  - FedCM 동의 화면의 IdP 계정 관리·개인정보·약관 링크 출처 설명을 config에서 well-known 파일로 바꿉니다.
  - 판정: watch. 동일 IdP 테스트 조건의 링크 노출·목적지를 확인합니다. 설명 변경을 새 사용자 UI 출시로 취급하지 않습니다.

한국 제공·한국어 지원은 미확인입니다. 실기 검증은 미실행이며 실제 제품 버전·출시 여부는 확인되지 않았습니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-12.json) · [실험 색인](README.md)

소스 등록 mask: kOsDesktop (Windows·macOS·Linux·ChromeOS). [등록 근거](https://raw.githubusercontent.com/chromium/chromium/603939f193be6df2a497c6f6e92ea77bffc915f9/chrome/browser/about_flags.cc). 실제 제품·설치본 제공 범위는 별도 확인이 필요합니다.

## 2026-11-13 소스 변경

FedCM passive 로그인에서 처음 정보를 공유하는 계정의 동의 화면을 bubble에서 modal로 옮겨 IdP의 계정관리·개인정보처리방침·약관 링크를 보여줍니다. 기존 재방문 계정은 원래 흐름을 유지합니다.

단일 IdP·단일 신규 계정은 1회에서 2회 선택으로 바뀝니다. 여러 계정은 2회 선택을 유지하되 두 번째 동의가 modal에서 이뤄집니다. 같은 날 후속 commit은 별도 multiple-IdP flag가 켜진 경우 복수 IdP에도 적용합니다. 두 flag 조건이 충족되지 않은 복수 IdP 요청은 bubble에서 동의합니다. 2026-11-11의 기존 사건은 링크 출처를 well-known으로 바로잡은 설명 변경이었다. 이번은 passive 신규 계정의 실제 dialog 전환 코드와 복수 IdP 조건 변경이므로 기존 링크 기능의 최초 도입이 아니라 동작 변경이다.

- 소스 revision: `6562990bab15390e8ccca4a00f3ba421e46929c4`
- 플랫폼: Windows, macOS, Linux, ChromeOS. 소스 OS mask와 구현 경로 근거이며 설치본 제공 확인은 아닙니다.
- 한국 제공·한국어 지원: unknown. 실기 시험: 미실행.
- [기능 분석](../../features/chrome/fedcm-idp-links.md) · [사건](../../data/events/chrome-fedcm-passive-signup-modal-source-20261113.json)

- [[FedCM] Request passive mode sign-up permission in the modal dialog](https://github.com/chromium/chromium/commit/199a8e77c6b2f9e66f4fc00c44624706c118a16f)
- [[FedCM] Use the modal for passive mode sign-up with multiple IdPs](https://github.com/chromium/chromium/commit/6562990bab15390e8ccca4a00f3ba421e46929c4)
- [기존 IdP 링크 설명 변경 (2026-11-11, 신규 UI 출시 아님)](https://github.com/chromium/chromium/commit/542d7914a86f0915025d40e699fa2de876d36e7d)
