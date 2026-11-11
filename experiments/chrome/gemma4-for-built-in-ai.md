# gemma4-for-built-in-ai

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-08-07 | added | kOsDesktop | [fcc477caf217](https://github.com/chromium/chromium/commit/fcc477caf2177cf917b5b829495ef55e509fa0c0) |

[전체 목록](README.md)

## 2026-11-11 소스 변경

- 2026-11-11T01:56:20Z · [3e7f7899744f](https://github.com/chromium/chromium/commit/3e7f7899744fcc572be6b95252b44d661f3aa7d2)
  - 기존 Gemma 4 Built-in AI 옵션에 OnDeviceModelConversationBackend를 추가하고 LiteRT-LM Conversation backend를 설명에 명시합니다.
  - 판정: watch. 기존 옵션과 같은 장치·모델에서 첫 응답 지연·응답 품질을 비교할 빌드가 필요합니다. 새 모델 출시나 성능 향상으로 단정하지 않습니다.

한국 제공·한국어 지원은 미확인입니다. 실기 검증은 미실행이며 실제 제품 버전·출시 여부는 확인되지 않았습니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-12.json) · [실험 색인](README.md)

소스 등록 mask: kOsDesktop (Windows·macOS·Linux·ChromeOS). [등록 근거](https://raw.githubusercontent.com/chromium/chromium/603939f193be6df2a497c6f6e92ea77bffc915f9/chrome/browser/about_flags.cc). 실제 제품·설치본 제공 범위는 별도 확인이 필요합니다.
