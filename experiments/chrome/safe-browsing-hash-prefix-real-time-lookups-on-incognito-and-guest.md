# safe-browsing-hash-prefix-real-time-lookups-on-incognito-and-guest

소스 관찰과 실제 노출·동작 검증을 구분합니다.

## 2026-11-10 소스 변경

- 2026-11-10T19:13:55Z · [4b3dfe9063ac](https://github.com/chromium/chromium/commit/4b3dfe9063ac893aafc7dcffdabe0a0a0e6daf02)
  - 시크릿·게스트 모드에서 URL을 Safe Browsing 해시 접두사 실시간 조회로 검사하는 flag를 등록합니다. 같은 commit의 iOS 항목은 시크릿 모드만 명시합니다. 실제 출시·기본 활성화·각 플랫폼 게스트 지원을 뜻하지 않습니다.
  - 판정: watch. 네트워크 전송·프라이버시 안내·모드별 정책과 설치본 지원 근거를 확인하면 비교합니다.

소스 플랫폼: Android, ChromeOS, Linux, Windows, macOS; 실제 제품·설치본 지원 범위는 별도 확인이 필요합니다. 한국 제공·한국어 지원은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-11.json) · [실험 색인](README.md)
