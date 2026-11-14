# no-pause-media-on-headphone-unplug

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-06-15 | added | kOsAndroid | [157e636452a9](https://github.com/chromium/chromium/commit/157e636452a9ed1fb0f53e00b87b86a94aa2e28d) |

[전체 목록](README.md)

## 2026-11-14 · 정방향 flag로 교체

[공식 diff](https://github.com/chromium/chromium/commit/29a376fd8407a03555e63beee6b2e1485756bee9)에서 기존 flag를 제거하고 pause-media-on-headphone-unplug를 추가했습니다. Desktop Android의 연결 해제 시 정지 동작도 변경합니다. 과거 등록 이력은 유지하며 제거를 기능 철회로 해석하지 않습니다. [후속 기능](../../features/chrome/android-headphone-disconnect-pause.md).
