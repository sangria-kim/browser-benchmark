# Windows 웹 앱 최대화 시 인접 모니터 침범 수정

Feature ID: `whale-webapp-multimonitor`

Canonical feature: whale-webapp-multimonitor

## 2026-11-07 관찰: Desktop 5.41.429.3

공식 본문의 배포 표기는 2026-11-06 Stable/Beta다. 동일 URL의 최초 등록일 11/3과 구분하며, .2 Beta의 기존 기록을 변경하지 않는다. 한국 제공·한국어 지원은 각각 미확인, 실기 미실행이다.

- [whale-desktop-webapp-multimonitor-5-41-429-3-20261106](../../data/events/whale-desktop-webapp-multimonitor-5-41-429-3-20261106.json): 이전 .2의 2개 수정에는 없고 .3에서 추가된 구체 동작 수정. 모든 사이트·모니터 구성이 해결되었다고 일반화하지 않음.
  - P2: 캡처 결과 또는 다중 모니터 작업 배치의 구체 실패 회복.
  - 비교 질문: 서로 다른 배율의 모니터에서 웹 앱 최대화 경계는 정확한가?
  - 검증: Windows에서 서로 다른 해상도 듀얼 모니터를 좌우 배치하고 100%/150% 배율로 설정한다. 웹 앱을 각 모니터로 이동해 최대화·복원을 3회씩 반복한 뒤 모니터 좌우 순서를 바꿔 재실행한다.
  - 지표: 인접 모니터 침범 픽셀, 최대화 경계, 복원 크기·위치 오차
  - 준비도: conditional. 영향 사이트 또는 재현 디스플레이 조건 확보

[공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)
