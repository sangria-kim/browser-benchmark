# android-multiprofile-startup-data

소스 관찰 기록입니다. 최초 도입이나 설치본 제공을 뜻하지 않습니다.

## 2026-10-30 관찰

- 종류: registration; source revision: `b967e34f97b231956605bd92f31a20d86eb9e9e9`; commit 시각: 2026-10-29T22:03:19Z.
- 플랫폼: Android. 근거: about_flags.cc kOsAndroid.
- 관련 feature: `features::kAndroidMultiprofileStartupData`; 소스 기본값: disabled.
- 만료 milestone: 없음/미확인 → 165. 만료와 삭제만으로 출시·철회를 추정하지 않습니다.
- 선별: watch, P2, 시험 준비 conditional. Startup/profile isolation gate, not evidence of shipped multi-profile UX.
- 한국 제공·한국어 지원: 미확인. 설치본 노출·동작 시험: 미실행.
- 재검토: 공개 빌드 노출 또는 공식 배포·지원 조건이 확인될 때.
- [공식 diff](https://github.com/chromium/chromium/commit/b967e34f97b231956605bd92f31a20d86eb9e9e9) · [사건 JSON](../../data/events/chrome-android-multiprofile-startup-data-registration-b967e34f97b2.json)
