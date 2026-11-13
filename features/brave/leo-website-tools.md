# Brave Leo Website Tools

Feature ID: `brave-leo-website-tools`

기존 WebMCP 도구 실험은 이미 존재했다. Nov12 병합 PR은 Blink WebMCP runtime을 experimental에서 stable로 바꾸고 base-feature override 및 기본 활성화 테스트를 연결한다. 빌드 봇은 Nightly 1.102.2를 지목한다. 소스의 stable 문자열은 Brave Stable 채널 출시를 뜻하지 않는다. API/runtime 기본값 변경은 모든 Leo UI의 노출이나 도구 자동 승인 근거가 아니다.

공식 도움말은 Windows·macOS·Linux에서 HTTPS 사이트 도구를 대화에 연결해 사용한다고 설명한다. 이미 로그인한 일반 프로필에서 동작하며 AI browsing의 격리 프로필과 다르다. 도구 실행 인자를 확인하고 매번 묻기·현재 세션 허용·차단을 선택한다. 권한은 해당 대화와 사이트 연결 동안만 유지된다. 여러 사이트를 연결하면 대화 정보가 다른 사이트 도구로 전달될 수 있다.

## 조건과 불확실성

현재 도움말은 Brave 1.96+ 및 #enable-webmcp-testing 수동 활성화를 요구한다. Nov12 병합 소스는 기본 활성화로 바뀌었다. 버전별 문서 정합성·설치본 상태 미확인. 한국 제공·한국어·계정별 노출은 미확인이다. 직접 시험은 미실행이다.

## 이력

- [2026-11-12 Nightly 기본값 변경 근거](../../data/events/brave-webmcp-default-nightly-11022-20261112.json). 이전 실험을 최초 도입으로 재분류하지 않는다.
- [공식 사용법](https://support.brave.com/hc/en-us/articles/50132604817165-How-do-I-use-Website-Tools-in-Brave-Leo)
- [기본 활성화 PR](https://github.com/brave/brave-core/pull/40616)
