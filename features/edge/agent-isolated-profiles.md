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
