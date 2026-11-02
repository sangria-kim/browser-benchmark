# magichrome-passkey-signin

검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.

- 기간 시작 snapshot에 등록: 아니요
- 기간 종료 snapshot에 등록: 예
- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.
- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.

| UTC 날짜 | 사건 | OS mask | 공식 diff |
| --- | --- | --- | --- |
| 2026-07-24 | added | kOsLinux, kOsMac, kOsWin | [d16684037de3](https://github.com/chromium/chromium/commit/d16684037de3043c6038b78a8772d8fb6168e9b0) |
| 2026-07-24 | modified | kOsLinux, kOsMac, kOsWin | [fca207766046](https://github.com/chromium/chromium/commit/fca20776604652314f9f27fcc7d202aae7182970) |

[전체 목록](README.md)

## 2026-11-03 소스 관찰 — 18bebb374e8f

- 변경 시각(UTC): 2026-11-02T15:02:41Z
- MagiChrome passkey sign-in의 native Views QR banner 실험 경로·옵션을 제거. Autofill 경로와 feature는 유지되므로 패스키 로그인 전체 철회로 볼 수 없음.
- 선별: watch — 실험 내 로그인 진입 경로 축소를 관찰하며 정식 사용자 영향·배포 조건 확인이 필요.
- 재검토: 해당 revision 포함 설치본에서 flag 옵션·테스트 계정·QR 인증 기기 조건을 확보한 뒤 실제 진입 흐름을 확인할 때.
- 플랫폼 근거: Windows/macOS/Linux 소스 mask 및 ENABLE_DICE_SUPPORT guard. 실제 배포 범위는 미확인.
- 한국 제공·한국어 지원: 미확인. 실기 검증: 미실행.
- [공식 diff](https://chromium.googlesource.com/chromium/src/+/18bebb374e8f95e77f15c03f3166663b781c5a54^!) · [수집 범위](monthly/2026-11-source-index-2026-11-03.json)

## 2026-11-03 소스 관찰 — 86a738936fd1

- 변경 시각(UTC): 2026-11-02T15:12:09Z
- MagiChrome passkey sign-in의 단일 Autofill 옵션을 Finch 실험 4개 arm과 일치하는 옵션으로 교체하고 설명을 수정. 설치본 노출과 제품 배포는 미확인.
- 선별: watch — 패스키 로그인 진입 UX 비교 가치가 있으나 실험 arm의 설치본·계정·배포 조건과 재현 환경이 미확인.
- 재검토: 해당 revision 포함 설치본에서 flag 옵션·테스트 계정·QR 인증 기기 조건을 확보한 뒤 실제 진입 흐름을 확인할 때.
- 플랫폼 근거: Windows/macOS/Linux 소스 mask 및 ENABLE_DICE_SUPPORT guard. 실제 배포 범위는 미확인.
- 한국 제공·한국어 지원: 미확인. 실기 검증: 미실행.
- [공식 diff](https://chromium.googlesource.com/chromium/src/+/86a738936fd153aa01ad73addd550c8fe5e45bdf^!) · [수집 범위](monthly/2026-11-source-index-2026-11-03.json)
