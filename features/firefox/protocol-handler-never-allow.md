# 반복 링크 처리 요청을 영구 차단하는 선택지

## 2026-11-10 Stable 확대

기존 160 Beta에서 설명한 기능이 11/10 Release 노트에 수록됐다. 기능 전체 최초 도입이 아니라 Stable 확대 사건이다.

mailto 등 프로토콜 처리 등록을 반복 요청하는 사이트의 Never allow와 설정 관리. 일반 팝업 차단과 구분.

한국 제공·한국어 지원은 미확인. 직접 시험은 미실행입니다.

[변경 사건](../../data/events/firefox-protocol-handler-never-allow-stable-160-20261110.json)

- [Websites that repeatedly ask to handle email (mailto:) and other links can now be blocked with a new “Never allow” button, and blocked sites can be managed in Settings.](https://www.firefox.com/en-US/firefox/160.0/releasenotes/#note-792507)
- [기존 Beta의 선행 기능 설명과 대조](https://www.firefox.com/en-US/firefox/160.0beta/releasenotes/)

사용자 영향: 웹메일 등 링크 처리기 등록을 반복 요청하는 사이트를 지속 차단할 수 있다. 사용자는 매번 같은 요청을 닫지 않아도 되고 설정에서 차단 결정을 되돌릴 수 있다.

우선순위: 사이트의 반복 등록 요청과 외부 링크 처리 선택을 사용자 의도대로 유지하는 기본 통제이므로 P1로 둔다.
