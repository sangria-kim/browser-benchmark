# Chrome Contextual Tasks의 Android 기기 형태 조건 변경

- Feature ID: `chrome-contextual-tasks-form-factor-scope`
- 사건: `chrome-contextual-tasks-form-factor-scope-source-20261112`
- 업무: pc, mobile; AI 관련: true
- 현재 상태: source-main 실험 관찰, P2 / conditional. 설치본 노출·실기 동작 미확인.
- 우선순위 이유: 실험의 기기 형태 조건을 정확히 구분해야 비교 설계 오류를 피할 수 있습니다. 설치본 제공 여부는 미확인입니다.
- [사건 JSON](../../data/events/chrome-contextual-tasks-form-factor-scope-source-20261112.json) · [contextual-tasks-override-show-bottom-sheet-on-large-screen](../../experiments/chrome/contextual-tasks-override-show-bottom-sheet-on-large-screen.md)

## 확인된 변화

Android Contextual Tasks UI를 desktop form factor에 한정합니다. Phone·tablet에서는 Java 초기 검사와 C++ 검사 모두 false를 반환하도록 바꾸고 bottom-sheet override flag를 제거합니다. 변경 전에도 Android에서 항상 켜져 있던 UI가 아닙니다. SidePanel, ContextualTasks, Rearchitecture, SidePanelRearchitecture 중 하나가 활성화되어야 C++ 검사 결과가 true였고 네 feature의 Android 기본값은 모두 disabled입니다. 변경 전 설치본의 실제 노출·동작은 확인하지 않았습니다.

변경 후 IS_ANDROID 분기에서 DEVICE_FORM_FACTOR_DESKTOP이 아니면 먼저 false를 반환합니다. Desktop form factor에서도 기존 네 feature의 OR 조건은 그대로 필요합니다. Java의 native 초기화 전 검사도 DeviceInfo.isDesktop() AND cached SidePanel flag로 바뀝니다. 따라서 phone/tablet은 해당 소스에서 feature를 켜도 UI eligibility가 false입니다. 이는 소스 실험 조건 변경이며, 출시된 일반 Android 기능의 철회를 입증하지 않습니다.

- 소스 commit 시각: 2026-11-12T18:34:22Z.
- 근거 확인일: 2026-11-13 KST. 발표일·실제 적용일은 미확인.
- 소스 등록·삭제는 단독으로 출시·철회 증거가 아니다.

## PM 비교 질문

비교 대상은 같은 플랫폼·조건의 Chrome과 삼성 브라우저다. 삼성 브라우저의 해당 기능 지원 여부는 먼저 확인하며 미지원이면 대체 흐름 또는 미지원으로 기록한다.

동일 페이지의 Contextual Tasks 진입·대화 이어가기 과제를 Android desktop form factor와 phone/tablet에서 어떻게 제공하는가?

## 동일 조건과 재현 절차

같은 플랫폼·소스 또는 제품 버전·계정·정책·네트워크·입력 자료를 고정한다. 비교 브라우저의 해당 과제 지원 여부부터 확인하며 삼성 브라우저의 지원 여부나 내부 계획은 추정하지 않는다.

1. 같은 소스 버전의 Android desktop form factor와 phone/tablet 조건을 준비한다.
2. Contextual Tasks 관련 flags와 계정 조건을 같게 맞춘다.
3. 같은 페이지에서 메뉴·툴바 진입 노출 및 UI eligibility를 확인한다.
4. 지원되는 조건에서만 대화 이어가기와 원문 복귀 조작을 비교한다.

## 지표와 완료 기준

- 진입 노출 여부
- 대화 시작 성공 여부
- 원문 복귀 조작 수
- device 조건 불일치 오류

완료 기준: desktop form factor와 phone/tablet 결과를 구분해 기록하고 source 조건과 설치본 동작을 혼동하지 않는다.

아직 위 시험을 수행하지 않았다. 한국 제공·한국어 지원·기기·계정별 실제 접근 조건은 unknown이다. 소스 관찰, 설치본 노출, 동작 검증을 별도로 기록한다.

## 공식 근거

- [[Contextual Tasks] Restrict Contextual Tasks UI to Desktop Android](https://github.com/chromium/chromium/commit/99b78dcd2ff7bd79daa6d2716c1446202c5b9a16)
- [변경 전 Contextual Tasks feature 기본값과 IsContextualTasksUIEnabled](https://github.com/chromium/chromium/blob/afc190faa71b1328cf03c2dca286f119fc8801cc/components/contextual_tasks/public/features.cc)
- [변경 후 Android desktop form factor 검사](https://github.com/chromium/chromium/blob/99b78dcd2ff7bd79daa6d2716c1446202c5b9a16/components/contextual_tasks/public/features.cc)
- [Java pre-native 검사와 host 조건 변경 diff](https://github.com/chromium/chromium/commit/99b78dcd2ff7bd79daa6d2716c1446202c5b9a16)
