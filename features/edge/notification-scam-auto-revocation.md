# 사기 탐지에 따른 알림 권한 자동 해제

- Feature ID: `edge-notification-scam-auto-revocation`
- 관찰: 2026-11-04 KST
- 범위: 156 Stable. 2026년 10월 배포부터라는 공식 설명이며 정확한 적용일은 미공개.
- 알림 차단 자체의 최초 도입이 아니라 탐지한 사기와 발신 사이트를 연결하는 자동 해제·재시작 안내·복구 흐름. OS별 배포 및 한국 제공은 미확인.
- 설치본·한국 단말·벤치마크: 미실행.

## 이력

- [2026-11-04 분석](../../reports/2026-11-04.md): [사건 `edge-notification-scam-auto-revocation-156`](../../data/events/edge-notification-scam-auto-revocation-156.json).
- 공식 근거·PM 판정·한국 조건은 연결 사건과 분석에 기록.

## 2026-11-04 KST 신규성 정정

Edge 152.0.4191.53(2026-08-27) 공식 Stable 노트에 SmartScreen 탐지 연계 자동 해제·사용자 안내·설정 복구의 controlled rollout이 이미 명시되어 있다. 11/2 글의 156 설명과 단계 차이가 밝혀지지 않아 신규성 검증 대기로 정정한다. 156에서 Scareware 경로가 최초 추가됐다고 단정하지 않는다.

- [공식 Edge 152 선행 근거](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-archive-stable-channel#version-1520419153-august-27-2026-stable---main-release)
- 현재 판정: `pending_verification`, priority `null`. 기존 selected/P1 판정은 사건의 correction_history에 보존한다.
- 위 156 범위·흐름 설명은 최초 관찰 기록이며 최초 출시 근거가 아니다. 추가 공식 근거 전 신규 출시로 재알림하지 않는다.
