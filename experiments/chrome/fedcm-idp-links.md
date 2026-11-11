# fedcm-idp-links

소스 관찰과 설치본 노출·실제 동작 검증을 구분합니다.

## 2026-11-11 소스 변경

- 2026-11-11T18:34:35Z · [542d7914a86f](https://github.com/chromium/chromium/commit/542d7914a86f0915025d40e699fa2de876d36e7d)
  - FedCM 동의 화면의 IdP 계정 관리·개인정보·약관 링크 출처 설명을 config에서 well-known 파일로 바꿉니다.
  - 판정: watch. 동일 IdP 테스트 조건의 링크 노출·목적지를 확인합니다. 설명 변경을 새 사용자 UI 출시로 취급하지 않습니다.

한국 제공·한국어 지원은 미확인입니다. 실기 검증은 미실행이며 실제 제품 버전·출시 여부는 확인되지 않았습니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-12.json) · [실험 색인](README.md)

소스 등록 mask: kOsDesktop (Windows·macOS·Linux·ChromeOS). [등록 근거](https://raw.githubusercontent.com/chromium/chromium/603939f193be6df2a497c6f6e92ea77bffc915f9/chrome/browser/about_flags.cc). 실제 제품·설치본 제공 범위는 별도 확인이 필요합니다.
