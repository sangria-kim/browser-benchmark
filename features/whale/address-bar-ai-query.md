# 주소창의 ChatGPT·Claude 검색어 직접 전송

Canonical feature: whale-address-bar-ai-query

## 2026-11-07 관찰: Desktop 5.41.429.3

공식 본문의 배포 표기는 2026-11-06 Stable/Beta다. 동일 URL의 최초 등록일 11/3과 구분하며, .2 Beta의 기존 기록을 변경하지 않는다. 한국 제공·한국어 지원은 각각 미확인, 실기 미실행이다.

- [whale-desktop-address-bar-ai-query-5-41-429-3-20261106](../../data/events/whale-desktop-address-bar-ai-query-5-41-429-3-20261106.json): 주소창에서 ChatGPT·Claude 검색 시 검색어가 바로 전달됨. AI 서비스나 검색 제공자 지원 자체의 최초 도입으로 확대하지 않음.
  - P2: AI 질문 입력의 화면 전환·재입력 감소를 비교 가능.
  - 비교 질문: 같은 질문을 주소창과 AI 사이트에서 보낼 때 조작 수·질의 보존·전송 인지가 어떻게 다른가?
  - 검증: 같은 Desktop 프로필에서 ChatGPT·Claude를 검색 제공자로 각각 지정하거나 공식 제공 선택지를 확인한다. 한글·영문 질문을 입력하고 전송 전 취소, 실제 전송, 뒤로 이동 후 재시도를 각 3회 수행한다. 서비스 직접 입력 경로와 로그인/비로그인 조건을 나눠 비교한다.
  - 지표: 전송 조작 수, 질의 문자·공백 보존, 취소 시 네비게이션 여부, 재시도 중복 제출, 목적지 인지
  - 준비도: conditional. 검색 제공자 설정·로그인 조건·설치본 노출 확인

[공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)
