# history-page-refresh

소스 관찰과 설치본 노출·직접 동작은 구분합니다.

## 2026-11-09 소스 변경

- 2026-11-09T12:54:12Z · [84c5a918ba80](https://github.com/chromium/chromium/commit/84c5a918ba80c212e52a19eea41db53cad8ef6a2)
  - 방문 기록 페이지의 시각적 개편을 위한 history-page-refresh flag를 Desktop에 등록합니다. 소스 기본값은 비활성이며 (DesktopGlowUp 또는 WebuiRefresh2026)와 HistoryPageRefresh가 함께 켜져야 합니다. 구체적인 화면·배포 버전·효과는 이 등록으로 확인되지 않습니다.
  - 판정: watch · 새 화면과 실제 탐색·재방문 과제 변화가 확인되면 비교합니다.

플랫폼 근거: ChromeOS, Linux, Windows, macOS. 소스 조건이며 실제 설치본 지원을 보장하지 않습니다. 한국 제공·한국어 지원·최소 버전은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-10.json) · [실험 색인](README.md)
