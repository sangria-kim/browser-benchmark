# send-tab-to-self-no-target-device-qr-code

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-09-28 | added | kOsLinux, kOsMac, kOsWin | [6cb0b9658f1f](https://github.com/chromium/chromium/commit/6cb0b9658f1f88979ba0da0342ed620b6f768693) |

[전체 목록](README.md)

## 2026-11-09 소스 변경

- 2026-11-09T21:25:52Z · [69a03519802e](https://github.com/chromium/chromium/commit/69a03519802e67112945dcc4c7c88633e17e5845)
  - 대상 기기가 없는 Send Tab to Self의 QR promo를 CrossDeviceSigninFromDesktopFollowup으로 연결하며 기존 flag를 제거했으나 같은 날 146b65cf에서 되돌렸습니다. 이 일시적 소스 변경은 출시·철회 근거가 아닙니다.
  - 판정: excluded · 후속 확정 구현과 제품 배포 근거가 확인되면 재검토합니다.
- 2026-11-09T21:43:00Z · [146b65cf049e](https://github.com/chromium/chromium/commit/146b65cf049e947806e91fa9832b2b0f4f9d4ad4)
  - 앞선 69a03519 변경을 되돌려 send-tab-to-self-no-target-device-qr-code 등록·설명·만료 정보를 복구합니다. 재등록이며 최초 도입이나 새 배포로 세지 않습니다.
  - 판정: excluded · 후속 확정 구현과 제품 배포 근거가 확인되면 재검토합니다.

플랫폼 근거: Linux, Windows, macOS. 소스 조건이며 실제 설치본 지원을 보장하지 않습니다. 한국 제공·한국어 지원·최소 버전은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-10.json) · [실험 색인](README.md)

## 2026-11-10 소스 변경

- 2026-11-10T12:00:00Z · [a86bdcec8b1d](https://github.com/chromium/chromium/commit/a86bdcec8b1d6c1bcf50cad064dfa62cf483ddbb)
  - 이전 변경·되돌림 뒤 Send Tab to Self의 전용 QR code flag 제거 변경을 재적용합니다. QR 안내 기능 폐지나 최초 출시로 해석하지 않습니다.
  - 판정: excluded. 사용자 흐름이나 지원 범위가 실제로 달라진 근거가 있을 때 재검토합니다.

소스 플랫폼: Linux, Windows, macOS; 실제 제품·설치본 지원 범위는 별도 확인이 필요합니다. 한국 제공·한국어 지원은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-11.json) · [실험 색인](README.md)
