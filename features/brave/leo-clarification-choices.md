# Leo가 모호한 요청에 선택지를 제시하는 흐름을 Desktop 1.99.55 정식 노트에 포함

- Feature ID: `brave-leo-clarification-choices`
- 채널/버전: stable / 1.99.55
- 범위: 공식 latest의 Desktop 절. GitHub의 Android/iOS 설치 artifact 안내 및 QA label을 Stable 모바일 출시 근거로 사용하지 않는다.
- 선별: selected / P2 / pm-selection-v2

## 이력

### 2026-11-05 공식 발표, 2026-11-06 KST 확인

- [사건 데이터](../../data/events/brave-leo-clarification-choices-stable-1-99-55-20261105.json) · [날짜별 보고](../../reports/2026-11-06.md)
- 이전: 공식 이슈에는 Android 1.99.53 Beta 및 Windows 1.99.54 QA 선행 확인이 있다.
- 현재: Desktop 1.99.55 정식 배포 노트에서 선택형 명확화 흐름을 확인했다. 선택 대신 직접 입력하는 우회 경로도 이슈 시험 계획에 있다.
- 신규성: 11/4 artifact-only 1.99.55 prerelease=true와 비교해 11/5에 prerelease=false 및 기능별 정식 노트가 확인됨. Beta 선행 기록과 구분하며 최초 발명이라 표현하지 않는다.
- 발표일: 2026-11-05. 실제 사용자별 적용일: 미확인.

## PM 검토

- 사용자 영향 및 선정 이유: 사용자 의도 확인을 버튼 선택과 자유 입력으로 수행하는 구체적 AI 과제 변화.
- 비교 질문: 동일한 모호한 요청에서 선택지를 통한 의도 확정과 직접 입력이 성공률·추가 입력 횟수에 어떤 차이를 만드는가?
- 우선순위: P2. 구체적인 탐색·대화·멀티태스킹 조작의 개선으로 P2 비교 과제. AI라는 이유로 P1을 부여하지 않는다.
- 벤치마크 준비: conditional. 모호한 요약·일정 초안 등 비실행 과제 5개로 선택형 질문 유도→선택/직접입력 각 반복→최종 결과가 의도와 일치하는지 기록. 외부 행동은 수행하지 않는다.
- 측정: 조작·입력 횟수, 완료 시간, 목표 일치·오류 여부. 원문 탐색은 출처 식별·원문 이동 성공도 기록한다.
- 완료 기준: 노출 여부와 시험 환경을 먼저 기록하고 과제를 양쪽에서 같은 조건으로 반복할 수 있어야 한다. 미노출은 그 환경의 결과로만 남긴다.
- 실기: 미실행. 외부 공식 QA를 자체 검증 결과로 간주하지 않는다.

## 한국 적용과 조건

- 한국 제공·한국어: 미확인. Leo 일반 도움말은 초기 opt-in과 무료 이용 시 계정 불필요를 설명한다. 이 기능별 모델·구독·지역·한국어 조건은 미확인.
- 한국 적용일: 미확인. 계정·구독·연령 등 명시되지 않은 조건을 추정하지 않는다.
- 재검토: 정식 설치본 노출·동작 및 한국어/모델 조건 확인. 모바일은 독립 공식 Stable 근거 확인 후 재검토.

## 공식 근거

- [출시 노트](https://brave.com/latest/)
- [근거 2](https://github.com/brave/brave-browser/releases/tag/v1.99.55)
- [근거 3](https://github.com/brave/brave-browser/issues/59649)
- [근거 4](https://github.com/brave/brave-browser/issues/59649#issuecomment-6623368822)
- [근거 5](https://support.brave.app/hc/en-us/articles/20958609786637-How-do-I-use-Brave-Leo)
