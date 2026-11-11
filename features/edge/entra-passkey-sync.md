# Entra 패스키 동기화의 모바일 Stable 확대

- Feature ID: `edge-entra-passkey-sync`
- 플랫폼: Android, iOS
- 직접 시험: 미실행

10/29 Mobile Beta에 있던 Entra ID 패스키 동기화가 11/9 Android·iOS Stable 157.0.4341.42 노트에 추가됐다. 기업용 패스키 동기화 전체의 최초 도입은 아니다.

## 기능 이력

- 2026-11-09: [Entra 패스키 동기화의 모바일 Stable 확대](../../data/events/edge-entra-passkey-sync-mobile-stable-157-20261109.json). Mobile Beta 10/29 선행, Desktop Stable 149(6/4) controlled rollout 선행 및 151(7/31) 반복 안내를 본문으로 대조했다. 새 사건은 11/9 Mobile Stable 확대이며 모든 소비자 계정 지원으로 일반화하지 않는다.

## 제공 조건

- accounts: Microsoft Entra ID 업무·학교 계정
- channel: Stable; 점진적 배포 및 앱스토어 반영 지연 가능
- policy: 저장 정책과 PasswordManagerEnabled 정책의 영향을 확인해야 함
- source_conflict: 최신 한국어·영어 공식 FAQ 모두 MSA·Entra 지원으로 일치. 한국어 문서만으로 한국 출시일·한국어 UI 제공을 확정하지 않음.
- subscription: 추가 요금제 조건 미공개
