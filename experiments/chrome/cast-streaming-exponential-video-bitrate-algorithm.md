# cast-streaming-exponential-video-bitrate-algorithm

소스 관찰과 실제 노출·동작 검증을 구분합니다.

## 2026-11-10 소스 변경

- 2026-11-10T00:25:31Z · [20edaa832b9b](https://github.com/chromium/chromium/commit/20edaa832b9b8107c13e288d9edc31ce27a46c13)
  - Cast Streaming 지수형 비트레이트 알고리즘 flag와 실험 옵션을 제거하면서 새 점진적 대역폭 감소 feature를 소스 기본 활성화로 추가합니다. 실제 품질 향상이나 제품 배포를 검증한 결과가 아닙니다.
  - 판정: watch. 동일 네트워크에서 혼잡 전후 비트레이트·회복 시간·영상 품질을 검증할 빌드가 확인되면 비교합니다.

소스 플랫폼: ChromeOS, Linux, Windows, macOS; 실제 제품·설치본 지원 범위는 별도 확인이 필요합니다. 한국 제공·한국어 지원은 미확인, 실기 검증은 미실행입니다.

[관련 소스 사건](monthly/2026-11-source-index-2026-11-11.json) · [실험 색인](README.md)
