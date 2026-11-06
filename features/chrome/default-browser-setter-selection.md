# Chrome 기본 브라우저 지정 안내 실험

- Feature ID: `chrome-default-browser-setter-selection`
- 업무: PC. AI 관련: false.
- 상태: 소스 실험 관찰 / P2 / conditional. 버전·채널·설치본 노출은 미확인.

## 이력

- 2026-11-07 KST 관찰: Windows 11의 기존 기본 브라우저 지정 흐름에 Set default 버튼을 가리키는 안내 버블 옵션 추가.
- 기존 flag 및 shell integration·visual guide의 최초 도입은 이번 사건이 아니다.
- [사건](../../data/events/chrome-annotated-default-browser-setter-20261106.json) · [상세 보고](../../reports/2026-11-07.md) · [flag](../../experiments/chrome/default-browser-setter-selection.md)
- [공식 diff](https://chromium.googlesource.com/chromium/src/+/b15c57b8d29d899032cc36c0de9cfde74aaf1512^!); source commit 2026-11-06T18:38:52Z. 발표일·실제 적용일은 미확인.

## 비교 질문

Windows 11에서 기본 브라우저 지정 시 OS 설정 창으로 이동한 뒤 안내 버블이 없는 기존 방식보다 완료 시간·잘못된 클릭·미완료 비율이 달라지는가? 삼성 브라우저의 동일 안내 지원은 별도 확인한다.

Windows 10과 기타 플랫폼은 shell_integration으로 fallback한다. 한국 제공·한국어·실기·계정·지역 조건은 미확인이다. 삼성 브라우저 동등 기능은 별도 확인한다.
