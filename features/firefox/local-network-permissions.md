# Android 로컬 네트워크·기기 접근 권한의 Stable 확대

## 2026-11-10 Stable 확대

기존 160 Beta에서 설명한 기능이 11/10 Release 노트에 수록됐다. 기능 전체 최초 도입이 아니라 Stable 확대 사건이다.

Android. 일회 허용/차단과 사이트별 기억을 구분. 설정 > 사이트 설정에서 기기 앱/서비스와 로컬 네트워크를 각각 관리.

한국 제공·한국어 지원은 미확인. 직접 시험은 미실행입니다.

[변경 사건](../../data/events/firefox-local-network-permissions-stable-160-20261110.json)

- [Websites now need permission before connecting to devices on the local network or to apps and services on the device. Learn more](https://www.firefox.com/en-US/firefox/android/160.0/releasenotes/#note-792488)
- [기존 Beta의 선행 기능 설명과 대조](https://www.firefox.com/en-US/firefox/160.0beta/releasenotes/)
- [Permission choices and site settings](https://support.mozilla.org/kb/control-personal-device-local-network-permissions-firefox-android)

사용자 영향: 사이트가 같은 Wi-Fi 장치나 휴대폰 내부 서비스에 연결하기 전에 사용자가 허용·차단을 선택한다. 방문 자체로 내부 연결에 동의했다고 간주하지 않고, 한 번 허용과 사이트별 기억을 분리할 수 있다.

우선순위: 웹사이트와 개인 기기·로컬 네트워크의 경계가 바뀌므로 프롬프트 이해도와 허용 범위 오인 가능성을 우선 확인한다.
