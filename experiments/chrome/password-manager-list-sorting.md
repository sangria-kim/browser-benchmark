# password-manager-list-sorting

소스 관찰과 설치본 노출·실제 동작 검증을 구분합니다.

## 2026-11-11 소스 변경

- 2026-11-11T10:43:45Z · [8e8bf5630f67](https://github.com/chromium/chromium/commit/8e8bf5630f67252122c9bf0b3a102299c6b6dfa3)
  - Desktop Password Manager의 저장 비밀번호·패스키를 이름, 마지막 사용일, 생성일로 정렬하는 실험 flag를 등록합니다.
  - 판정: watch. 같은 자격 증명 집합에서 최근 사용·생성 항목 찾기 시간과 오류를 비교할 수 있습니다. 실제 UI 접근 조건은 미확인입니다.

한국 제공·한국어 지원은 미확인입니다. 실기 검증은 미실행이며 실제 제품 버전·출시 여부는 확인되지 않았습니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-12.json) · [실험 색인](README.md)
