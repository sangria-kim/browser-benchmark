# 저장한 PDF 수학 콘텐츠 접근성 개선

## 2026-11-10 Stable 확대

기존 160 Beta에서 설명한 기능이 11/10 Release 노트에 수록됐다. 기능 전체 최초 도입이 아니라 Stable 확대 사건이다.

웹페이지 PDF 저장 시 MathML을 보조 기술이 읽도록 개선. 모든 PDF·일반 이미지 수식 인식과 다름.

한국 제공·한국어 지원은 미확인. 직접 시험은 미실행입니다.

[변경 사건](../../data/events/firefox-pdf-mathml-accessibility-stable-160-20261110.json)

- [Pages saved as PDF now make mathematical content (MathML) accessible to assistive technology such as screen readers.](https://www.firefox.com/en-US/firefox/160.0/releasenotes/#note-792506)
- [기존 Beta의 선행 기능 설명과 대조](https://www.firefox.com/en-US/firefox/160.0beta/releasenotes/)

사용자 영향: 웹페이지를 PDF로 보관·공유한 뒤에도 화면읽기 도구가 MathML 수식을 해석할 수 있도록 한다. 보이는 모양만 저장하는 것과 달리 수학 구조의 접근성 유지가 목적이다.

우선순위: 수학 콘텐츠를 저장해 읽는 특정 접근성 과제에 의미가 있어 P2로 두고 실제 PDF 읽기 순서를 검증한다.
