# seccomp-filter-gpu-sandbox

검증 상태: 소스 관찰. 설치본·동작·버전 미확인.

## 2026-11-01 수집 — bbc7faad4959

- 소스 commit 시각: 2026-10-30T23:41:16Z
- 등록부: added
- 소스 OS mask: 없음 → kOsAndroid
- Android GPU 프로세스 seccomp-bpf sandbox flag를 소스에 등록. 출시·기본 활성화·실기 효과는 미확인.
- 선별: excluded — 소스 보안 격리 실험이며 검증된 사용자 과제 변화나 비교 지표 근거가 아직 없음.
- 재검토: 공식 제품 배포·사용자 영향 또는 실행 가능한 검증 조건이 확인될 때.
- [공식 diff](https://chromium.googlesource.com/chromium/src/+/bbc7faad495945a3dd1d60dc2b41d03ea2e90171^!) · [수집 범위](monthly/2026-10-source-index-2026-11-01.json)
- [정본 사건 JSON](../../data/events/chrome-seccomp-filter-gpu-sandbox-registration-bbc7faad4959.json)
