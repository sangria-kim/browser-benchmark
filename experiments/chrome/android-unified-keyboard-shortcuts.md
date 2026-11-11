# android-unified-keyboard-shortcuts

소스 관찰 기록입니다. 최초 도입이나 설치본 제공을 뜻하지 않습니다.

## 2026-10-30 관찰

- 종류: registration; source revision: `1ab53bc5148b29d0c6bf96a42e229986b4147fb2`; commit 시각: 2026-10-29T17:25:54Z.
- 플랫폼: Android. 근거: about_flags.cc kOsAndroid.
- 관련 feature: `chrome::android::kAndroidUnifiedKeyboardShortcuts`; 소스 기본값: disabled.
- 만료 milestone: 없음/미확인 → 170. 만료와 삭제만으로 출시·철회를 추정하지 않습니다.
- 선별: watch, P2, 시험 준비 conditional. Gate for upcoming unified C++ shortcut handling; not evidence that unified shortcuts are available.
- 한국 제공·한국어 지원: 미확인. 설치본 노출·동작 시험: 미실행.
- 재검토: 공개 빌드 노출 또는 공식 배포·지원 조건이 확인될 때.
- [공식 diff](https://github.com/chromium/chromium/commit/1ab53bc5148b29d0c6bf96a42e229986b4147fb2) · [사건 JSON](../../data/events/chrome-android-unified-keyboard-shortcuts-registration-1ab53bc5148b.json)

## 2026-11-10 소스 변경

- 2026-11-10T22:53:54Z · [719f89df6cfa](https://github.com/chromium/chromium/commit/719f89df6cfa45aa8557f56d7753aace6807c24b)
  - Android 통합 키보드 단축키의 관련 feature namespace를 chrome::android에서 ui로 이동합니다. 등록 ID는 유지되며 이번 소스 이동만으로 사용자 동작 변경을 주장하지 않습니다.
  - 판정: excluded. 키보드 동작·지원 범위 변경의 별도 근거가 있으면 재검토합니다.

소스 플랫폼: Android; 실제 제품·설치본 지원 범위는 별도 확인이 필요합니다. 한국 제공·한국어 지원은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-11.json) · [실험 색인](README.md)

## 2026-11-11 소스 변경

- 2026-11-10T23:30:36Z · [79ec77d85f8b](https://github.com/chromium/chromium/commit/79ec77d85f8bdd631d1a76218ebb9c5c938fe885)
  - Android 통합 키보드 단축키 feature namespace 이동을 되돌립니다. 사용자 기능의 신규 도입·삭제가 아닙니다.
  - 판정: excluded. 사용자 동작이나 플랫폼 지원 변경의 별도 근거가 있으면 재검토합니다.

한국 제공·한국어 지원은 미확인입니다. 실기 검증은 미실행이며 실제 제품 버전·출시 여부는 확인되지 않았습니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-12.json) · [실험 색인](README.md)
