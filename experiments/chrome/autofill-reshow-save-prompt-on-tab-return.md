# autofill-reshow-save-prompt-on-tab-return

소스 관찰과 설치본 노출·직접 동작은 구분합니다.

## 2026-11-09 소스 변경

- 2026-11-09T15:28:10Z · [edd45d5ad919](https://github.com/chromium/chromium/commit/edd45d5ad919368b5fc8d4ea99bca2ffca7046ff)
  - iOS에서 다른 탭이나 외부 안내 링크를 본 뒤 원래 탭으로 돌아오면 보류 중인 Autofill AI 저장·카드 저장 안내를 다시 표시하려는 기본 비활성 flag를 등록합니다. 이 commit은 flag·설명·시험 설정이며 실제 동작 구현·설치본 노출·배포는 별도 확인이 필요합니다.
  - 판정: watch · 실제 구현과 시험 가능한 빌드가 확인되면 중단 후 저장 흐름을 비교합니다.

플랫폼 근거: iOS. 소스 조건이며 실제 설치본 지원을 보장하지 않습니다. 한국 제공·한국어 지원·최소 버전은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-10.json) · [실험 색인](README.md)
