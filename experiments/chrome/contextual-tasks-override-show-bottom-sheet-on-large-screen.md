# Chrome contextual-tasks-override-show-bottom-sheet-on-large-screen

- Flag ID: `contextual-tasks-override-show-bottom-sheet-on-large-screen`
- 상태: source-main에서 flag 제거 확인. 출시 기능 철회로 단정하지 않는다.
- 플랫폼: 제거된 등록은 kOsAndroid이다.
- [기능 분석](../../features/chrome/contextual-tasks-form-factor-scope.md) · [사건 JSON](../../data/events/chrome-contextual-tasks-form-factor-scope-source-20261112.json)

2026-11-12 source commit에서 large-screen bottom sheet override flag를 제거했다. 함께 바뀐 Contextual Tasks UI 검사는 Android desktop form factor를 요구한다. 변경 전에도 관련 네 feature 중 하나가 켜져야 했고 Android 기본값은 모두 disabled였다. 변경 후에도 desktop form factor에서 기존 feature 조건이 필요하며 phone/tablet은 false이다. 실제 설치본의 과거·현재 동작을 시험하지 않았다.

[공식 diff](https://github.com/chromium/chromium/commit/99b78dcd2ff7bd79daa6d2716c1446202c5b9a16). 한국 제공·한국어 지원은 unknown이다.
