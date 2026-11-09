# Performance detector 종료 계획

Feature ID: `edge-performance-detector`

## 2026-11-06 발표

Edge 158.0.4370.7 Beta 노트는 Performance detector와 PerformanceDetectorEnabled 정책의 종료를 버전 164에서 예상한다고 설명합니다. 실제 종료일과 적용 빌드는 미확인입니다. 158에서 이미 제거됐다는 뜻이 아닙니다.

기존 기능은 문제 탭을 감지하고 해결 권고를 표시합니다. 정책 문서의 지원은 Windows·macOS 107 이상이며 Android·iOS를 포함하지 않습니다. 이 정책 지원 범위를 최종 종료 범위와 동일시하지 않습니다.

- 판정: selected / P1 / conditional. 기존 진단 경로의 종료 예고를 비교하는 과제입니다.
- 발표와 근거 확인일은 구분합니다. 최초 기록은 2026-11-08 KST입니다.
- 한국 제공·한국어 지원·한국 적용일·대체 UI: 미확인.
- 설치본·직접 동작·벤치마크: 미실행.
- [사건 JSON](../../data/events/edge-performance-detector-retirement-plan-164-20261106.json) · [상세 분석과 시험 설계](../../reports/2026-11-08.md) · [Edge 158](../../releases/edge/158/README.md)

## 이전 근거와 구분

Beta archive의 107.0.1418.8(2022-10-13)은 해당 정책의 도입입니다. 158.0.4370.7(2026-11-06)의 종료 계획과 다른 사건입니다. 예고의 최초 대외 공개 시점을 모든 과거 revision에서 확정한 것은 아닙니다. 실제 제거는 후속 공식 근거로 별도 판단해야 합니다.

## 공식 출처

- [Beta 158.0.4370.7 / Performance detector retirement](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-beta-channel#version-158043707-november-6-2026)
- [PerformanceDetectorEnabled 정책](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/performancedetectorenabled)
- [Beta archive / 107.0.1418.8](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-archive-beta-channel)
