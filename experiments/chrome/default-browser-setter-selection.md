# default-browser-setter-selection

- Flag ID: `default-browser-setter-selection`
- Source feature: `default_browser::kDefaultBrowserSetterSelection`
- 이번 관찰의 workflow identity: `chrome-default-browser-setter-selection`. flag와 제품 기능의 일반적 1:1 대응을 의미하지 않는다.
- 이번 옵션 최초 관찰: 2026-11-06T22:56:00Z; 기존 flag 최초 등록일은 이번 조사에서 판정하지 않음.
- revision: `b15c57b8d29d899032cc36c0de9cfde74aaf1512`; commit 시각 2026-11-06T18:38:52Z.
- 활성화 후보: `chrome://flags/#default-browser-setter-selection`에서 `with Annotated Shell Integration (Windows 11)` 선택. 설치본 노출 미확인.
- 소스 조건: 해당 옵션의 실효 동작은 Windows 11 이상. 기존 등록부의 desktop OS mask는 모든 플랫폼에서 안내가 작동한다는 뜻이 아니다.

## 2026-11-07 KST 옵션 관찰

기존 shell_integration·visual_guide에 annotated_shell_integration 추가. 설정의 Set default 버튼을 가리키는 버블과 기존 OS 지정 흐름을 함께 실행한다. 안내가 종료돼도 흐름은 계속될 수 있으며 지정 결과는 shell integration 결과를 따른다. Windows 10과 다른 OS는 기존 방식으로 fallback한다.

[공식 diff](https://chromium.googlesource.com/chromium/src/+/b15c57b8d29d899032cc36c0de9cfde74aaf1512^!) · [전체 소스 색인](monthly/2026-11-source-index-2026-11-07.json) · [사건](../../data/events/chrome-annotated-default-browser-setter-20261106.json) · [기능 이력](../../features/chrome/default-browser-setter-selection.md)

검증: 직전 성공 snapshot부터 현재 3개 경로 patch를 순차 재생하여 공식 종료 snapshot과 byte-identical임을 확인. 관련 setter·unit test 소스 검토 완료. 빌드·단위 테스트 실행·설치본·한국 지원·실기 검증은 하지 않았다.
