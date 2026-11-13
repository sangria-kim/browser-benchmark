# Desktop 온디바이스 음성인식 API의 Stable 확대

## 2026-11-10 Stable 확대

기존 160 Beta에서 설명한 기능이 11/10 Release 노트에 수록됐다. 기능 전체 최초 도입이 아니라 Stable 확대 사건이다.

Desktop 40개 언어. Android 음성인식과 클라우드 원격 인식은 지원하지 않는다고 MDN 명시. 지원 언어 전체 목록·한국어·모델 다운로드 조건 미확인.

한국 제공·한국어 지원은 미확인. 직접 시험은 미실행입니다.

[변경 사건](../../data/events/firefox-on-device-speech-recognition-stable-160-20261110.json)

- [The SpeechRecognition interface of the Web Speech API is now supported, providing on-device, real-time speech-to-text in 40 languages.](https://www.firefox.com/en-US/firefox/160.0/releasenotes/#note-792492)
- [기존 Beta의 선행 기능 설명과 대조](https://www.firefox.com/en-US/firefox/160.0beta/releasenotes/)
- [APIs / On-device speech recognition](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/160)

사용자 영향: 지원 웹사이트가 음성을 기기 안에서 실시간 텍스트로 바꿀 수 있다. 음성인식이 브라우저 전체의 음성 비서나 Android 지원을 뜻하지 않으며, 서버에 음성을 보내는 경로와 구분된다.

우선순위: 음성의 처리 위치와 사용자 동의가 개인정보 경계에 직접 연결되므로 모델·언어 조건과 권한 안내를 우선 검증한다.

## 2026-11-13 지원 근거 보완

11월 10일 확인 때는 한국어와 모델 다운로드 조건을 미확인으로 기록했다. 당시 조건 원문은 다음과 같다.

> Desktop 40개 언어. Android 음성인식과 클라우드 원격 인식은 지원하지 않는다고 MDN 명시. 지원 언어 전체 목록·한국어·모델 다운로드 조건 미확인.

이번 공식 도움말은 다국어 음성인식 모델에 한국어를 명시한다. 영어 모델은 약 140 MB이며, 기타 지원 언어 모델은 약 785 MB다. 필요한 모델이 없으면 다운로드 전에 사용자 허용을 요청한다. 모델 설치 후에는 로컬에서 오프라인 인식도 가능하다. AI Controls에서 차단하면 설치 모델을 제거한다. 음성 입력에는 사이트의 마이크 사용 권한도 별도로 필요하다.

한국 지역 제공과 실제 설치본 노출은 미확인이다. 직접 시험은 미실행이다. 이번 기록은 기존 Firefox 160 Stable 사건의 지원 조건 보완이다. 한국어의 신규 도입일이나 한국 출시일은 확인하지 않았다.

- [공식 지원 언어 및 모델 다운로드 도움말](https://support.mozilla.org/en-US/kb/speech-recognition-firefox)
- 기존 근거 확인: 2026-11-10T23:16:21.389826+00:00
- 새 근거 확인: 2026-11-12T23:20:29.603776+00:00
