# 수집·보고서 생성 전체 기록

상세 보고서가 **생성된 날과 생성되지 않은 날을 함께** 확인하는 공개 기록입니다. 보고서 미생성 사유와 수집 오류·미확인 범위를 분리합니다. `selected 0건`은 **확인한 범위에서 새 상세 분석 대상으로 선정한 사건이 없다**는 뜻이며, 모든 출처에 변화가 없거나 수집이 완전했다는 뜻이 아닙니다.

- 날짜 기준: **Asia/Seoul**. 원본 자료의 UTC 관찰 시각·공지일·배포일과 구분합니다.
- 최초 소급 정리: 2026-11-05. [확인 기준 commit](https://github.com/sangria-kim/browser-benchmark/commit/9e8517a35a24fa3d8614b7fb677f910a8b29465e)의 날짜별 보고서, 수집 JSON, 수집 상태 및 공개 commit 이력으로 확인한 내용만 옮겼습니다.
- 범위: 2026-10-28·29의 기존 보고서 샘플, 2026-10-30~11-05의 저장된 수집 결과, 관련 보완·정정 기록입니다. **기록 도입 이전의 모든 자동화 시도·중단·재시도를 복원한 로그는 아닙니다.** 공개 근거가 없는 실행과 이전 날짜의 미생성 이유는 확인 불가이며 추정하지 않습니다.
- 같은 날짜에 보완·정규 수집·정정이 있으면 별도 행으로 남깁니다. 문서 편집 commit 자체를 새 수집 실행으로 세지 않습니다. 이후 모든 수집·보고 생성 시도는 아래 [갱신 규칙](#갱신-규칙)을 따릅니다.
- 이메일 주소·전달 결과·메시지 ID·계정/연결 ID·비공개 checkpoint·비공개 게시 상태·인증 정보·사내 자료는 포함하지 않습니다. 이 문서는 메일 발송 이력을 대신하지 않습니다.

## 최근 결과

**2026-11-06: 상세 보고서 생성, 확인 범위 신규 selected 17건, 수집은 부분 완료.** Vivaldi·Opera 주간 보조 관찰, Brave 정식 채널, Edge 새 탭과 Chrome 소스 실험을 분석했습니다. Chrome Enterprise·소스 증분·Brave API 접근은 복구했으나 ChromeStatus 과거 단계·Whale 제품 소개·일부 한국 출처는 미완료입니다. [상세 보고서](2026-11-06.md) · [출처별 사유](../data/collection/2026-11-06.json)

## 날짜별 전체 이력

`—`는 해당 없음 또는 집계 근거 없음이며, 0건과 다릅니다. 보고서가 있는 날도 수집 범위는 부분일 수 있습니다. 각 행의 수치는 그 실행 시점의 판정이며 뒤의 정정 행을 함께 읽습니다.

| 날짜 (KST) / 기록 | 보고서 결과 | 새 selected | 생성·미생성 이유 | 오류·부분 확인·범위 제한 | 공개 근거 |
| --- | --- | ---: | --- | --- | --- |
| 2026-10-28 / 기존 보고서 | [기존 보고서 있음](2026-10-28.md) | — | 기존 분석을 공개용 샘플로 가져온 기록. 당시 실행 결과를 새로 검증한 것이 아님. | 원 실행의 전체 상태·재시도는 확인 불가. 샘플 게시 시 출처 재검증·실기 미실행. | [샘플 추가 commit](https://github.com/sangria-kim/browser-benchmark/commit/4587c2be99ccd3d61b188cf14459c98c56dbfa41) (게시일 10/29 KST) |
| 2026-10-29 / 기존 보고서 | [기존 보고서 있음](2026-10-29.md) | — | 기존 분석을 공개용 샘플로 가져온 기록. 당시 실행 결과를 새로 검증한 것이 아님. | 원 실행의 전체 상태·재시도는 확인 불가. 샘플 게시 시 출처 재검증·실기 미실행. | [샘플 추가 commit](https://github.com/sangria-kim/browser-benchmark/commit/50ec471acd894c2a80bacd4ba1ea466e11154e29) |
| 2026-10-30 / 과거 이력·색인 정리 | 새 보고서 생성 안 함 | — | 기존 보고서 2건을 유지하고 Chrome flag 과거 이력·릴리스·업무별 색인을 정리. 새 기능 선정을 위한 정규 수집과 구분. | about_flags 1,169 commit 검증 범위 외 독립 파일 이력·PM 선별·실기 등 미완료. | [수집 상태](../docs/collection-status.md), [아카이브 commit](https://github.com/sangria-kim/browser-benchmark/commit/e663ca58c57e957aa5db70d59837ccdd676baf9e) (10/30 00:41 KST) |
| 2026-10-30 / 정규 수집 | [보고서 생성](2026-10-30.md) | 2 | Edge 실행 중 재호출·Opera WebAI를 선정. | 부분 완료. Brave Android 최신 상세·중간 사전배포 열거, Whale 제품 본문, Opera 일부 본문 등 미확인. 실기 미실행. | [수집 JSON](../data/collection/2026-10-30.json), [commit](https://github.com/sangria-kim/browser-benchmark/commit/41a30a5cb9ce4f501322759bc56d9411afc1e6f0) |
| 2026-10-31 / 정규 수집 | **미생성** | 0 | 일반·보안·빌드 변경과 기존 사건은 제외. Chrome 소스 변화는 watch, 과거 누락 복구는 새 출시로 세지 않음. | 부분 완료. Whale 제품 본문 접근·렌더링 실패, Brave Android 최신 상세·ChromeStatus 이력·Microsoft 한국 아카이브 미확인. 정기 주간 출처는 예정 전. | [수집 JSON](../data/collection/2026-10-31.json), [commit](https://github.com/sangria-kim/browser-benchmark/commit/5400a062489b64e5df5cf32541f47e2eaa3eaff4) |
| 2026-11-01 / 정규 수집 | **미생성** | 0 | 반복 발표·기존 항목, 소스 보안 실험·기존 활성화 gate 정리는 새 상세 분석 대상에서 제외. | 부분 완료. Brave Android 최신 상세·Whale 동적 제품 화면·ChromeStatus 전체 이력·Microsoft 한국 아카이브 미확인. 주간 출처는 예정 전. | [수집 JSON](../data/collection/2026-11-01.json), [commit](https://github.com/sangria-kim/browser-benchmark/commit/31dafe16e8d748c8c55da33e63ed4a56e74b6acf) |
| 2026-11-02 / 정규 수집 | **미생성** | 0 | ChromeStatus SVG textPath 목록 누락은 개별 API 존속과 상태 상충으로 검증 대기. 출시·철회로 단정하지 않음. 나머지 기존 항목·과거 이력 보완은 재선정하지 않음. | 부분 완료. Brave Android·Whale 제품·Microsoft 한국·ChromeStatus 이력 미완료. Gitiles 일부 502/503·시간 초과는 공식 mirror로 보완. 주간 출처는 예정 전. | [수집 JSON](../data/collection/2026-11-02.json), [commit](https://github.com/sangria-kim/browser-benchmark/commit/5c956bc38d99fcc42da022924320029e800bb6d2) |
| 2026-11-03 / Whale 누락 보완 | **미생성** | 0 | Desktop·Android 44개 항목을 보완. Android 4.1의 신규성 대조가 남아 당시에는 선정하지 않음. 이후 정규 수집 결과와 별개. | 부분 완료. 이전의 “Whale 최신 발표 10/1”은 연구소·정적 제품 문구에 한정되며 홈페이지 별도 공지 전체에 일반화할 수 없음을 정정. | [수집 상태](../docs/collection-status.md), [보완 commit](https://github.com/sangria-kim/browser-benchmark/commit/d5250becafd030a4dd73feedff866350008dcd22), [검증 수정](https://github.com/sangria-kim/browser-benchmark/commit/c2bfde4b1d3aeaef29b44302753c9f9981d3c867) |
| 2026-11-03 / 정규 수집 | [보고서 생성](2026-11-03.md) | 2 | Whale Android 4.1 설정 검색·시크릿 캡처 옵션을 원문·신규성 대조 후 선정. | 부분 완료. ChromeStatus GPC API 403, Brave Android 최신 상세·Microsoft 한국 아카이브·Whale 제품 영상 등 미확인. 주간 출처는 예정 전. | [수집 JSON](../data/collection/2026-11-03.json), [commit](https://github.com/sangria-kim/browser-benchmark/commit/35058584c0ab1b2b75b4dc8bf09dec550e8a2c5e) |
| 2026-11-04 / 정규 수집 | [보고서 생성](2026-11-04.md) | 13 → 정정 후 12 | Whale Desktop Beta, Edge 알림 제어, Firefox 패스키 수정, Chrome 소스 실험 분석. Edge 1건은 아래 정정 참조. | 부분 완료. GPC API 접근 실패, Microsoft 한국·Brave 일부 상세·Whale 영상 미확인. Whale Stable/Beta 문서 상충 유지. 실기 미실행. | [수집 JSON·정정](../data/collection/2026-11-04.json), [최초 commit](https://github.com/sangria-kim/browser-benchmark/commit/26ee8103fc191f0f439f696b0170b7cc7eb93516) |
| 2026-11-04 / Edge 신규성 정정 | 기존 보고서 수정 | — | 최초 selected 13건 중 자동 알림 해제 1건을 pending_verification으로 전환. 현재 selected 12건. 새 수집·새 출시가 아님. | Edge 152 선행 공식 근거가 있어 156 최초 도입·배포 확대 여부는 미확인. 최초 판정 이력은 보존. | [정정 보고서](2026-11-04.md), [정정 commit](https://github.com/sangria-kim/browser-benchmark/commit/4663962fcdf1abddd0753e783a9fc5cd26a71007) |
| 2026-11-05 / 정규 수집 | **미생성** | 0 | 확인 범위에서 새 selected 없음. Chrome 빌드 참조·Brave 아티팩트에는 개별 새 기능 근거가 없고 Firefox·Edge·Whale 기존 사건은 반복 제외. | 부분 완료. Chrome Enterprise 본문 실패, flags 증분 이력·replay 미완료, ChromeStatus·블로그·한국 출처 부분 확인, Brave API 전송 실패, Edge Mobile 본문 미조회, Whale 제품 JS shell. Opera·Vivaldi는 정규 예정 전이며 참고 조회를 완료로 세지 않음. | [수집 JSON](../data/collection/2026-11-05.json), [commit](https://github.com/sangria-kim/browser-benchmark/commit/9e8517a35a24fa3d8614b7fb677f910a8b29465e) |

| 2026-11-06 / 정규 수집·주간 보조 관찰 | [보고서 생성](2026-11-06.md) | 17 | Vivaldi Stable·Opera 창별 탭 상태, Brave 정식 노트, Edge 새 탭, Chrome 소스 실험을 신규 사건으로 선정. 기존 기능·베타 선행 이력과 구분. | 부분 완료. ChromeStatus 전체 과거 이력·일부 신규성, Whale 제품 소개, Microsoft 한국 아카이브·일부 한국어 도움말 미완료. Opera Mobile 예정 전. 실기 미실행. | [수집 JSON](../data/collection/2026-11-06.json), [보고서](2026-11-06.md) |

## 갱신 규칙

1. **보고서를 만들지 못해도 이 기록을 갱신한다.** 기존 수집·보고 자동화의 매 시도와 별도 보완·정정마다 날짜·기록 구분·보고서 결과·확인 범위 신규 selected 수·구체적 사유·오류/미완료 범위·공개 근거를 남긴다. 같은 날짜의 재시도는 `재시도 2` 등으로 구분해 최초 실패를 지우지 않는다. 실제 실행을 확인할 수 없는 날짜·중단은 `확인 불가`로 쓰며 미실행이나 성공으로 추정하지 않는다.
2. 결과는 `생성`, `기존 보고서 수정`, `미생성`, `생성 실패`, `보류`, `확인 불가`를 구분한다. 미생성은 `적합한 새 feature 없음`, `검증 대기`, `과거 보완만 수행` 등 실제 이유를 적는다. 생성 실패·보류는 실패 단계(수집/신규성 검증/보고 작성 등), 공개 가능한 오류 요약, 영향을 받은 출처, 재개 조건을 적는다. 사유가 여러 개이면 함께 남긴다.
3. **선정 결과와 수집 범위는 별개다.** 출처 접근 실패를 `적합 feature 없음`으로 바꾸지 않는다. 선별을 수행하지 못했다면 수치는 `확인 불가`이며 0이 아니다. 부분 수집에서 선정 0건이면 반드시 `확인 범위에서 0건`과 미확인 출처를 함께 적는다. 예정 전 생략은 오류·성공·변화 없음과 구분한다.
4. 새 selected 사건이 있을 때만 `reports/YYYY-MM-DD.md`를 생성한다. 이 기록의 추가·수정만으로 빈 상세 보고서나 별도 알림을 만들지 않는다. 보고서가 생기면 [보고서 색인](README.md)과 해당 업무별 색인도 갱신한다.
5. 확인된 수집 JSON·보고서·공개 commit 또는 공식 근거를 연결하고 날짜·건수·정정 이력과 대조한다. 보고서 링크는 실제 파일이 있을 때만 만든다. 예정·시도·도구 응답만으로 생성 완료라 쓰지 않는다. 정정 시 이전 판정과 정정 사유를 남긴다.
6. 저장소에 접근할 수 없어 이 파일도 갱신하지 못하면 공개 가능한 사유를 비공개 환경에 보존하고 접근 복구 후 실제 발생 날짜의 누락 기록을 보충한다. 이 파일만으로 모든 중단을 자동 감지할 수는 없다. 기록을 저장하지 못한 상황을 기록 완료로 표시하지 않는다.
7. 계정·수신자·메일/게시 상태·checkpoint 등 비공개 운영 정보, 비공개 실행 ID·로그·접속 URL·토큰은 복사하지 않는다. 공개된 제품 출처와 보고서 생성 판단에 필요한 최소 사실만 쓴다. 원래 상세 보고·발송 기준, 주기와 승인 범위는 유지한다.

### 새 기록 양식

아래는 빈 양식이며 실행 결과가 아닙니다. 실제 값과 존재하는 링크로 채운 뒤 날짜별 표에 추가하고 `최근 결과`도 갱신합니다.

| 날짜 (KST) / 기록 | 보고서 결과 | 새 selected | 생성·미생성 이유 | 오류·부분 확인·범위 제한 | 공개 근거 |
| --- | --- | ---: | --- | --- | --- |
| YYYY-MM-DD / 정규·보완·정정·재시도 구분 | 생성 / 수정 / 미생성 / 생성 실패 / 보류 / 확인 불가 | 확인한 수 또는 확인 불가 | 실제 사유와 필요 시 재개 조건 | 수집 범위·실패 단계/출처·미확인·예정 전 생략 | 실제 보고서·수집 자료·공개 근거 링크 |

운영 기준: [수집 및 게시 지침](../docs/collection-policy.md) · [자동화 적용용 공개 지시문](../docs/automation-prompt.md) · [상세 수집 상태](../docs/collection-status.md)

