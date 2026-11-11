# Leo의 문맥 기반 후속 질문 제안을 Desktop 1.99.55 정식 노트에 포함

- Feature ID: `brave-leo-followup-suggestions`
- 채널/버전: stable / 1.99.55
- 범위: 공식 latest의 Desktop 절. GitHub의 Android/iOS 설치 artifact 안내 및 QA label을 Stable 모바일 출시 근거로 사용하지 않는다.
- 선별: selected / P2 / pm-selection-v2

## 이력

### 2026-11-05 공식 발표, 2026-11-06 KST 확인

- [사건 데이터](../../data/events/brave-leo-followup-suggestions-stable-1-99-55-20261105.json) · [날짜별 보고](../../reports/2026-11-06.md)
- 이전: Android 1.99.53 Beta 및 Windows 1.99.54의 공식 QA 댓글에 선행 동작 기록이 있다.
- 현재: 정식 Desktop 노트가 후속 제안 개선을 명시한다. 이슈 시험 계획은 응답 뒤 주제 관련 제안과 선택 후 대화 지속을 확인한다.
- 신규성: 11/4 artifact-only 1.99.55 prerelease=true와 비교해 11/5에 prerelease=false 및 기능별 정식 노트가 확인됨. Beta 선행 기록과 구분하며 최초 발명이라 표현하지 않는다.
- 발표일: 2026-11-05. 실제 사용자별 적용일: 미확인.

## PM 검토

- 사용자 영향 및 선정 이유: 응답 이후 다음 탐색으로 넘어갈 때 직접 타이핑해야 하는 부담과 제안 품질을 비교할 수 있다.
- 비교 질문: 같은 조사 과제에서 후속 제안 선택과 직접 질문 입력의 과제 완료 시간·편집 필요 횟수·관련성이 어떻게 다른가?
- 우선순위: P2. 구체적인 탐색·대화·멀티태스킹 조작의 개선으로 P2 비교 과제. AI라는 이유로 P1을 부여하지 않는다.
- 벤치마크 준비: conditional. 같은 설명 질문 5개로 응답 후 제안 노출·개수·관련성 기록→제안 한 개 선택→맥락 유지·최종 답의 유용성 확인. 제안이 항상 3개라고 단정하지 않는다.
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
- [근거 3](https://github.com/brave/brave-browser/issues/59650)
- [근거 4](https://github.com/brave/brave-browser/issues/59650#issuecomment-6623643598)
- [근거 5](https://support.brave.app/hc/en-us/articles/20958609786637-How-do-I-use-Brave-Leo)

## Android 정식 노트 근거 보완

2026-11-11 확인한 1.99.55 공식 릴리스의 Android 절과 Android changelog에도 이 기능이 명시된다. 기존 Desktop 범위 원문은 당시 근거로 보존한다. 새 노트 추가를 11/11 모바일 출시로 해석하지 않으며 최초 적용일·한국 조건은 미확인이다.

[Android 공식 항목](../../releases/brave/1.99.55/android-feature-references.json)
