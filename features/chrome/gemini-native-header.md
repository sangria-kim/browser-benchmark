# Chrome iOS · Gemini 네이티브 헤더

- Feature ID: `chrome-gemini-native-header`
- 2026-11-15 소스: Gemini SDK 헤더를 Chrome 네이티브 헤더로 바꾸는 flag와 helper를 등록했다. 실제 UI 렌더링·제품 출시는 이 변경만으로 확인되지 않는다.
- `gemini-native-header` / `kGeminiNativeHeader`: 기본 비활성화. `kIOSGeminiBottomSheetMigration`과 함께 활성화해야 한다.
- iOS 대상. Windows·Android 변경이 아니다. 한국 제공·한국어 지원·설치본 노출은 미확인, 직접 시험은 미실행.
- 비교 질문: 네이티브 헤더가 이동·닫기·되돌리기와 브라우저/AI 구분을 바꾸는가?

[소스 실험](../../experiments/chrome/gemini-native-header.md) · [사건](../../data/events/chrome-ios-gemini-native-header-source-20261115.json)
