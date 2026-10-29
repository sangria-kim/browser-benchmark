# Edge Accelerated App Launch

- Canonical feature key: `edge-accelerated-app-launch`
- Browser: edge; platform: Windows; workstreams: pc; AI: false.

## 이력

### 2026-10-30 확인

Windows의 기존 Edge 프로세스 직접 호출로 warm launch의 중간 프로세스 생성을 줄이는 배포 단계.

10월 28일 KB5127936의 Normal rollout에 New로 기재. 10월 29일 제품 발표와 구분하며 Edge 150 최초 출시일을 뜻하지 않음.

- 발표: 2026-10-29; 이번 기록의 적용 단계: 2026-10-28. 최초 도입일은 별도 미확인입니다.
- 범위: Windows 11 25H2/26H2/26H1 with October non-security update or later; the inspected KB package covers 25H2/26H2.
- 선별: selected / P2 / conditional. 지원 OS 업데이트에서 새 배포 단계가 확인되고 링크·시작 메뉴의 대기 시간을 동일 조건으로 비교할 수 있습니다.
- 한국 제공·한국어 지원·한국 적용일: 미확인. 실기 시험: 미실행.
- 비교 질문: 삼성 브라우저 Windows판은 해당 OS 가속 등록을 지원하는가? 미지원이더라도 같은 warm launch 과제에서 지연과 프로세스 비용은 어떤가?
- 재검토 조건: 26H1 패키지 및 국내 테스트 환경, 다음 보안 업데이트 포함 여부가 공식 확인될 때.
- [상세 보고서와 제안 시험](../../reports/2026-10-30.md) · [사건 JSON](../../data/events/edge-accelerated-app-launch-windows-kb5127936-20261028.json)

## 공식 출처

- [공식 근거 1](https://blogs.windows.com/msedgedev/2026/10/29/edge-is-faster-on-windows-with-accelerated-app-launches/)
- [공식 근거 2](https://support.microsoft.com/en-us/servicing/os/windows-11/2026/10/kb5127936-windows-11-25h2-26h2-update)
- [공식 근거 3](https://learn.microsoft.com/en-us/windows/apps/develop/launch/accelerated-launch)
