# fedcm-active-mode-multiple-identity-providers

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-08-18 | added | kOsDesktop | [990d8a478511](https://github.com/chromium/chromium/commit/990d8a4785111b229e46ef54b449a889c9540743) |

[전체 목록](README.md)

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
