# glic-daisy-chain-new-tabs

## 기존 snapshot의 역사 기록

아래 등록 여부와 당시 판정은 원래 snapshot 구간의 기록입니다. 이후 삭제와 현재 소스 판단은 하단의 2026-11-08 이력을 참고하세요.

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 예
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-08-13 | modified | kOsAndroid, kOsDesktop | [b92b51be641c](https://github.com/chromium/chromium/commit/b92b51be641c6d8579d2ae2ab785ffb0761fb92f) |

[전체 목록](README.md)

## 2026-11-08 소스 이력

- [공식 commit a89dd3d8245c](https://github.com/chromium/chromium/commit/a89dd3d8245cfbb3fe7670397efa456a8144514b) · UTC 2026-11-07T00:37:59Z
- 만료된 chrome://flags 등록을 제거하지만 underlying base::Feature는 Finch 실험을 위해 유지합니다. 사용자 작업 흐름의 제거나 배포 확대를 입증하지 않습니다.
- 판정: excluded / pm-selection-v2. 이 소스 변경을 신규 제품 사건으로 선정하지 않습니다.
- 한국 제공·한국어·설치본: 미확인. 직접 시험: 미실행.
- [소스 근거 색인](monthly/2026-11-source-index-2026-11-08.json)
