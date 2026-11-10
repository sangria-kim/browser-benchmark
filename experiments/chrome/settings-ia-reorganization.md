# settings-ia-reorganization

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-10-16 | added | kOsAndroid | [001905a08f86](https://github.com/chromium/chromium/commit/001905a08f86ec8f18da33451fe3838b442591ab) |

[전체 목록](README.md)

## 2026-11-10 소스 변경

- 2026-11-10T21:24:48Z · [3bd925715845](https://github.com/chromium/chromium/commit/3bd9257158457e8342509d3d92fe248f6d594bb3)
  - Android settings-ia-reorganization을 단일 켜기/끄기 flag에서 Direction 1·2·3 실험 옵션으로 변경합니다. arm 값은 direction_1·direction_2·direction_3이며 각 화면 배치와 출시 여부는 미확인입니다.
  - 판정: watch. 세 옵션의 실제 화면과 설정 탐색 단계·오류 차이를 비교할 환경을 확보하면 재검토합니다.

소스 플랫폼: Android; 실제 제품·설치본 지원 범위는 별도 확인이 필요합니다. 한국 제공·한국어 지원은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-11.json) · [실험 색인](README.md)
