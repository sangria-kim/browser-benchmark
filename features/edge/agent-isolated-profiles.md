# 외부 AI 에이전트별 격리 프로필 정책 수록

- Feature ID: `edge-agent-isolated-profiles`
- 선별: watch / 우선순위: 미지정
- 관찰일: 2026-11-08 KST
- 공식 근거: https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-beta-channel
- 변경: 외부 AI 에이전트별 격리 프로필 정책 수록
- 판단: 공식 정책 본문에서 Windows158+의 에이전트 identity별 browsing data 격리 확인. 비설정 기본값은 버전·rollout에 따라 다르므로 일반 출시·기본 활성으로 단정하지 않음.
- 한국 제공·한국어 지원: 미확인. 실기 검증: 미실행.
- 출시일: 미확인. 문서 갱신일을 출시일로 사용하지 않음.
- 재검토: 구 정책과 과거 공식 기능 이력 비교, 적용 빌드·계정·한국 제공 확인

## 이력

- [2026-11-08 관찰 사건](../../data/events/edge-agent-profile-policy-158-20261106.json)

## 비교 질문

에이전트별 쿠키·로그인·기록이 사용자 및 다른 에이전트와 분리되는가?

## 2026-11-13 후속 확인

- 현재 판단: pending_verification. 위 과거 관찰과 원문은 유지한다.
- 이전에 공개된 정책 항목이 현재 158 Beta 노트와 정책 색인에는 표시되지 않는다. 명시적인 철회 설명이나 설치본 동작 근거가 없어 제품 기능 제거 또는 출시 취소로 해석하지 않는다.
- 과거 문서의 버전·OS·계정 조건이 현재 설치본에서도 유효한지는 미확인이다.
- 제품 철회 또는 한국 지원 변경을 단정하지 않는다. 실기 검증은 미실행이다.
- 재검토: 문서 복구 또는 명시적인 공식 정책 변경 설명.
- [후속 검증 대기 사건](../../data/events/edge-agent-profile-policy-document-omission-20261112.json)
