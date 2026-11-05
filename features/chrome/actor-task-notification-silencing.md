# Chrome Android Actor 작업 알림의 무음화 실험

- Feature ID: `chrome-actor-task-notification-silencing`
- 업무: mobile; AI 관련: true
- P2 우선순위 이유: 실험적으로 시작한 AI 작업의 알림 방해와 개입 요청 인지를 함께 비교할 가치가 있다. 전체 알림 정책이 아닌 특정 작업 흐름의 사용성 개선이므로 P2로 둔다.
- 현재 상태: 소스 실험 관찰, P2 / conditional. 제품 출시·설치본 노출 미확인.
- 소스 범위: Android의 experimental-triggering Actor 작업에만 적용하는 기본 비활성 실험. 일반 작업과 전체 Android 알림 정책으로 일반화하지 않는다.

## 이력

- 2026-11-06 KST 관찰: 첫 비경고 ACTING/REFLECTING 알림만 소리를 낼 수 있도록 상태를 추적한다. 준비·후속 진행·일시정지·사용자 입력 요청·경고·완료 알림은 무음으로 만들며 완료·clearAll 때 추적을 초기화한다.
- [사건 JSON](../../data/events/chrome-actor-notification-silencing-flag-20261105.json) · [상세 보고](../../reports/2026-11-06.md) · [flag 이력](../../experiments/chrome/actor-silence-notifications-after-first-working.md)
- [공식 diff](https://chromium.googlesource.com/chromium/src/+/2951e28c3f03b55e5b7b4a383bec73f84176456c^!); source commit 시각 2026-11-05T17:17:06Z. 발표일·실제 적용일은 미확인.

## 비교 질문

Android에서 AI 작업의 소리·진동 알림 수를 줄이면서 사용자 입력 요청·경고를 놓치지 않도록 하는 방식은 무엇인가? 동일한 작업과 알림 설정으로 비교할 수 있는가?

한국 제공·한국어 지원·실제 설치본·동작 결과는 미확인/미실행이다. 삼성 브라우저 지원 여부를 추정하지 않는다.
