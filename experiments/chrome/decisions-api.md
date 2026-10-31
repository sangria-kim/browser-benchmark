# decisions-api

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-10-08 | added | kOsDesktop | [8651d46cbd8a](https://github.com/chromium/chromium/commit/8651d46cbd8ad6a3ae4ed6859892094250e36f09) |

[전체 목록](README.md)

## 2026-10-31 수집 — 옵션·설명 변경

`eda174533f4bc781a97165bbd94af438c99184b1` (2026-10-30 06:44:47 UTC): 등록부 자체가 아닌 kDecisionsAPIChoices에 All Backends / EmbeddingGemma V1 / Gemma 4 on CPU 옵션을 복원했습니다. All Backends 또는 Gemma 4 on CPU 선택은 모든 Gemma 4 내장 AI API의 CPU 사용을 강제한다는 설명입니다.

[공식 diff](https://chromium.googlesource.com/chromium/src/+/eda174533f4bc781a97165bbd94af438c99184b1^!) · [전체 수집](monthly/2026-10-source-index-2026-10-31.json). 소스 관찰, 설치본·모델 접근 미확인, PM watch. 출시 사실이 아닙니다.

- 요약: Decisions API backend 선택 옵션 복원. Gemma4 CPU 옵션은 해당 계열의 다른 내장 API에도 영향을 줄 수 있음.
- [정규 사건 JSON](../../data/events/chrome-decisions-api-options_modified-eda174533f4b.json) · 한국 제공/한국어: 미확인, 실기 미실행.
