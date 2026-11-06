# 사이트별 검은 캡처·스크롤 캡처 실패 수정

Canonical feature: whale-page-capture

## 2026-11-07 관찰: Desktop 5.41.429.3

공식 본문의 배포 표기는 2026-11-06 Stable/Beta다. 동일 URL의 최초 등록일 11/3과 구분하며, .2 Beta의 기존 기록을 변경하지 않는다. 한국 제공·한국어 지원은 각각 미확인, 실기 미실행이다.

- [whale-desktop-page-capture-5-41-429-3-20261106](../../data/events/whale-desktop-page-capture-5-41-429-3-20261106.json): 이전 .2의 2개 수정에는 없고 .3에서 추가된 구체 동작 수정. 모든 사이트·모니터 구성이 해결되었다고 일반화하지 않음.
  - P2: 캡처 결과 또는 다중 모니터 작업 배치의 구체 실패 회복.
  - 비교 질문: 동일 사이트 캡처의 출력 성공률·완결성은?
  - 검증: 동일 Desktop OS에서 고정 헤더·긴 문단·스크롤 컨테이너를 포함한 비민감 테스트 페이지를 준비한다. 전체 스크롤/선택 영역 캡처를 각각 3회 반복하고 화면 기준과 대조한다. 영향 사이트가 알려지면 같은 절차로 추가한다.
  - 지표: 검은 결과 수/6회, 누락·중복 구간, 캡처 높이, 완료 시간
  - 준비도: conditional. 영향 사이트 또는 재현 디스플레이 조건 확보

[공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)
