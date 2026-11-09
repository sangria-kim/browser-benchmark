# link/script/style의 blocking=render 실험 지원 문서 추가

- Feature ID: `firefox-render-blocking`
- 선별: watch / 우선순위: 미지정
- 관찰일: 2026-11-08 KST
- 공식 근거: https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/160
- 변경: link/script/style의 blocking=render 실험 지원 문서 추가
- 판단: MDN 160 실험 절에 수록됐으며 dom.element.blocking.enabled는 기본 비활성이다. 문서 편집일은 출시일이 아니며 Stable 지원·설치본 동작은 미확인이다.
- 한국 제공·한국어 지원: 미확인. 실기 검증: 미실행.
- 출시일: 미확인. 문서 갱신일을 출시일로 사용하지 않음.
- 재검토: 공식 적용 시점·빌드·지원 범위와 변경 전후 비교 조건 확인

## 이력

- [2026-11-08 관찰 사건](../../data/events/firefox-render-blocking-pref-160-20261108.json)

## 비교 질문

동적 스타일·스크립트 로드 중 비스타일 화면 노출과 첫 렌더링 지연은 어떻게 달라지는가?

## 벤치마크 후보

동일 OS·기기·네트워크와 Firefox 160 시험 빌드에서 지연 stylesheet와 동적 script/style 삽입 페이지를 비교합니다. pref의 기본값·지원 빌드를 먼저 확인하고 off/on 조건을 분리합니다.

- 지표: 첫 렌더링 시간, 비스타일 프레임 수, 입력 반응성.
- 완료 기준: 동일 조건에서 반복한 화면·시간 기록과 기본값 확인.
- 상태: 시험 설계이며 직접 실행한 결과가 아닙니다.
