# Chrome Android · 외부 오디오 연결 해제 시 일시정지

**소스 관찰만 완료.** 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. Android 플랫폼이며 Windows/macOS의 데스크톱 Chrome 변경이 아닙니다.

이전 코드는 Desktop Android에서 연결 해제에 따른 일시정지를 건너뛰었습니다. 새 코드는 기기 형태 대신 기본 활성화된 PauseMediaOnHeadphoneUnplug를 확인합니다. 기존 부정형 no-pause flag는 제거하고 pause-media-on-headphone-unplug로 교체합니다. 일반 Android의 최초 일시정지 도입이나 제품 출시가 아닙니다.

- 소스 변경: 2026-11-14 01:45:20 UTC
- 제품 발표일·효력일: 미확인
- 한국 제공·한국어 지원: 미확인
- 실기 시험: 미실행. 공식 commit 작성자의 시험 서술과 별개입니다.
- 소스 기본값: 활성. 만료 milestone 180은 배포 버전이 아닙니다.
- 기존 이력: [no-pause flag](../../experiments/chrome/no-pause-media-on-headphone-unplug.md)의 6월 등록을 보존합니다.
- [공식 diff](https://github.com/chromium/chromium/commit/29a376fd8407a03555e63beee6b2e1485756bee9) · [사건](../../data/events/chrome-android-headphone-disconnect-pause-source-20261114.json)
