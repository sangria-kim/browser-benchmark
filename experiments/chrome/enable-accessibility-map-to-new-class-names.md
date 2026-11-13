# Chrome enable-accessibility-map-to-new-class-names

## 2026-11-13 소스 변경

ARIA role="note"를 일반 View 대신 android.accessibility.role.Note로 매핑하고, 활성 상태에서 별도 roleDescription을 빈 값으로 바꿉니다. TalkBack이 note 문자열에 의존하지 않도록 하는 기본 비활성 실험입니다.

이전에는 note 역할이 일반 View className과 roleDescription에 의존했습니다. 활성화하면 새 className과 빈 roleDescription을 반환합니다. 역할 매핑·트리 기대값 소스와 테스트 변경을 확인했으나 실제 TalkBack 발화와 한국어 인식은 시험하지 않았습니다.

- 소스 revision: `f2e94debbdceb2cd8d83c7e255f54486b8eb16a2`
- 플랫폼: Android. 소스 OS mask와 구현 경로 근거이며 설치본 제공 확인은 아닙니다.
- 한국 제공·한국어 지원: unknown. 실기 시험: 미실행.
- [기능 분석](../../features/chrome/android-accessibility-note-class.md) · [사건](../../data/events/chrome-android-accessibility-note-class-source-20261113.json)

- [[WAAM] Implement role="note" className mapping](https://github.com/chromium/chromium/commit/f2e94debbdceb2cd8d83c7e255f54486b8eb16a2)
