# actor-silence-notifications-after-first-working

- Flag ID: `actor-silence-notifications-after-first-working`
- 관련 source feature: `chrome::android::kActorSilenceNotificationsAfterFirstWorking`
- 연결한 product feature ID: `chrome-actor-task-notification-silencing`. 이 관찰의 workflow identity이며 모든 flag와 기능을 1:1로 연결한다는 뜻은 아님.
- 최초 관찰: 2026-11-05T22:53:24Z; source commit: 2026-11-05T17:17:06Z
- revision: `2951e28c3f03b55e5b7b4a383bec73f84176456c`
- 플랫폼: Android (소스 조건, 배포 증거 아님)
- 활성화 진입점: `chrome://flags/#actor-silence-notifications-after-first-working`. Android의 experimental-triggering Actor 작업에만 적용하는 기본 비활성 실험. 일반 작업과 전체 Android 알림 정책으로 일반화하지 않는다.
- 등록 시 expiry milestone: 160. 만료값은 출시·철회 시점이 아님.

## 2026-11-06 관찰

첫 비경고 ACTING/REFLECTING 알림만 소리를 낼 수 있도록 상태를 추적한다. 준비·후속 진행·일시정지·사용자 입력 요청·경고·완료 알림은 무음으로 만들며 완료·clearAll 때 추적을 초기화한다.

[공식 diff](https://chromium.googlesource.com/chromium/src/+/2951e28c3f03b55e5b7b4a383bec73f84176456c^!) · [월별 전체 이력](monthly/2026-11-source-index-2026-11-06.json) · [제품 기능 이력](../../features/chrome/actor-task-notification-silencing.md) · [선정 사건](../../data/events/chrome-actor-notification-silencing-flag-20261105.json)

검증: 3개 현재 파일의 전체 증분 diff를 순서대로 적용하여 공식 종료 snapshot과 일치 확인. 설치본 노출·한국 제공·한국어 지원·직접 동작 검증은 미확인/미실행.
