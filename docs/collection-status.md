# 수집 상태 — 2026-10-30 KST

## 이번에 저장한 결과

- about_flags.cc: 2026-06-01 00:00 UTC ~ 2026-10-29 15:00 UTC, 1,169 commit 전체 diff를 순서대로 재적용하고 공식 종료 snapshot과 일치 확인.
- literal flag ID 938개에 등록 520건·등록부 수정 160건·삭제 430건. 고유 신규 기능 수가 아니다. 같은 ID의 재등록·여러 변경을 포함한다.
- 직접 등록부 변경이 없는 206 commit도 월별 JSON에 보존. 상수·옵션 정의·전처리 조건 등을 개별 flag에 연결했다고 주장하지 않는다.
- Chrome Enterprise 156의 29개, 157의 28개 항목과 Firefox 159 Desktop/Android·160 Beta, Edge 156 Desktop/Mobile 공식 항목 색인.
- 기존 보고서 2건을 그대로 유지하고 PC/Mobile/AI 탐색 색인 추가.

## 아직 완료되지 않은 범위

- flag_descriptions.cc·flag-metadata.json만 단독 수정한 이력, 만료 milestone의 전체 추적.
- symbolic flag ID 및 등록부 바깥 정의의 개별 flag 연결, 설치본 노출·직접 동작 검증, 938개 flag의 PM 가치 선별.
- ChromeStatus 전체 웹 플랫폼 목록, 현재 색인보다 이전 버전의 전체 릴리스 backfill.
- Notion 전체 과거 보고서 이관, dots 자동화의 저장 대상 전환, 이메일·checkpoint 영속 상태 검증.

이전 세션의 수집 임시 파일은 현재 환경에서 찾지 못해 공식 이력을 다시 확보했다. 대화의 진행 설명만으로 파일 저장 완료를 판단하지 않았다. GitHub API 및 Chromium 원본 요청 제한은 공식 mirror로 보완했고 about_flags.cc 누락은 0건이다. 상세 revision과 hash는 [manifest](../experiments/chrome/manifest.json)에 기록한다.

## 다음 수집 시 재개 기준

about_flags.cc는 manifest의 end_revision 이후를 겹쳐 확인하고 source_revision으로 중복 제거한다. 다른 두 파일은 2026-06-01부터 별도 backfill해야 하며 이번 성공 checkpoint를 공유하지 않는다. 실패한 원천을 성공으로 표시하지 않는다. 월별 날짜는 UTC이고 보고 날짜는 Asia/Seoul이다.

## 2026-10-30 대상 확장 — 문서 반영

- Brave·Whale: 기존 매 실행 정규 수집 대상으로 추가.
- Opera·Vivaldi: 주 1회 보조 관찰 대상으로 추가. 마지막 성공 확인 후 7일 이상 지난 첫 기존 실행에 점검하고 실패 출처는 다음 실행에서 재시도.
- Safari는 제외. 공식 출처·제품 구분·한국 지원 절차 및 적용용 공개 지시문을 추가.
- 추가 4종의 릴리스 수집·baseline·실기 검증은 아직 미실행. 빈 결과와 성공 checkpoint를 생성하지 않음.
- dots 실제 자동화 설정은 사용자가 직접 변경 예정. 문서 게시를 설정 적용·수집 성공으로 간주하지 않음.


## 2026-10-30 실행 결과 (관찰 마감 2026-10-29 22:43 UTC)

규칙 커밋: `88a6300f57e4065836e99a87a4431e0b6829f978`. 기존 기록은 이전 시점의 상태로 보존한다. [출처별 범위](../data/collection/2026-10-30.json), [상세 보고서](../reports/2026-10-30.md).

- Chrome Releases 22개 공지, Enterprise 156/157 공식 API 본문 재확인, ChromeStatus 157 Preview 18항목. ChromeStatus 156/158 전체 이력과 Enterprise 이전 본문 해시 비교는 미완료.
- Edge 및 Firefox 현재 릴리스·개발 문서 확인. 이미 전달한 Gmail 자동완성·Smart Window·Firefox 160 Beta와 Edge 신규성 정정은 재알림하지 않았다.
- Brave·Whale 매회 범위를 최초 점검했다. Brave Android 고정 태그와 중간 사전배포 목록, Whale 제품 페이지 본문은 미확인이다. 실패 범위는 다음 실행에서 재시도한다.
- Opera·Vivaldi 주간 보조 관찰을 최초 수행했다. 성공한 출처의 다음 정기 점검은 2026-11-05 이후 첫 기존 실행이다. Opera Mini 원문 실패는 다음 실행에서 재시도한다. Vivaldi Android 전체 Snapshot 조사가 완료됐다는 뜻은 아니다.
- Chrome about_flags.cc: 기존 검증 종점 이후 7개 커밋의 diff를 추가 관찰했다. 기존 전체 스냅숏 replay 검증 결과와 새 관찰 결과를 분리했다. metadata는 최근 8개 diff와 6월 1일 과거 이력을 보완했고, 6월 2일부터 재개해야 한다. 6월 2일~10월 21일은 미완료다.
- flag_descriptions.cc는 2025-11-05 삭제된 경로로 확인했다. 현재 설명 헤더의 최근 연결 diff만 검토했으며 헤더 전체 과거 이력 완료를 주장하지 않는다.
- 한국 발표 아카이브 전체 확인과 기존 938개 flag의 한국 조건 확인은 미완료다. 새 관심 기능 및 기존 관심 기능 일부를 [한국 기준선](../data/korea/2026-10-30-baseline.json)에 기록했다. 기준선은 신규 출시 또는 알림 사건이 아니다.
- 모든 실기 검증은 미실행이다. selected 2건만 보고하며 watch·excluded·미확인도 원천 색인에 보존한다. Safari는 수집 대상에서 제외했다.

추가 확인 22:49 UTC: Brave 고정 태그 Android 파일 접근은 성공했으나 본문 최상단이 1.96.59여서 최신 Android 변경 미확인은 해소되지 않았다.

## 2026-10-31 실행 결과

규칙 커밋: `da65ff91c0f604fb1dba7737869fee3f9fe87e8a`, `pm-selection-v2`. [출처별 실제 관찰 시각·범위](../data/collection/2026-10-31.json). 기존 기록과 정정 이력은 유지합니다.

- 새 selected 사건 0건. 빈 날짜별 상세 보고서를 만들지 않았습니다. Chrome159 Dev 빌드, Edge156.0.4314.56/.58, Brave1.98.63 엔진 패치는 원천 색인에 보존하고 일반·보안 수정으로 제외했습니다. Firefox159/160 Beta, Gmail자동완성, EdgeAAL은 기존 사건입니다.
- Chrome Releases 최근7일21개 본문, Enterprise156 29개/157 26개, ChromeStatus156–158 총58개 그룹 항목을 저장했습니다. Enterprise157 목록2개 감소는 철회 증거가 아닙니다. 개별 ChromeStatus 최초 발표·단계 변화와 과거 전체 이력은 미완료입니다.
- Brave 공식 API33개 겹침 구간 릴리스 열거를 확보해 중간 열거 누락을 해소했습니다. Android1.98.60의13항목은 과거 누락 복구이며 새 출시가 아닙니다. 최신 Android delta 및 Whale 제품 안내 전체 본문은 미확인입니다. Whale 운영팀 발표와 댓글 날짜는 구분했습니다.
- Opera 모바일 실패 원문을 복구했습니다. 나이지리아 기존 무료 데이터 회고로 새 기능 제외. Opera Desktop/news·Vivaldi는 주간 예정 전 생략이며 성공·변화 없음이 아닙니다.
- Chrome 최신 고유8commit의 관련 diff를 확보했습니다. about_flags6개는 직전 관찰 revision부터 replay해 공식 종료 snapshot과 일치했습니다. 원래1169commit archive의 종점·hash·건수는 바꾸지 않았습니다. metadata6/2~6/8의81diff를 보완했고 다음 재개는6/9 00:00UTC입니다. 설명.cc는 요청기간 전에 삭제된 경로이며 후속.h 전체 과거 이력은 미완료입니다.
- AIM4개 flag의 Android mask 확장, 다운로드 Last-Modified 보존, 감독계정 재인증 followup, Decisions API 옵션 복원은 source-only watch입니다. Android mask는 일반 Android 배포 증거가 아니며 모든 설치본·한국 제공·한국어 지원·실기 결과는 미확인/미실행입니다.
- 한국 Google 최신 RSS는 겹침 범위까지 확인했고 Microsoft 한국 아카이브는 부분 확인입니다. 기존 기능의 주간 지원조건 점검은 아직 예정 전입니다. 접근 실패를 미지원 또는 변화 없음으로 기록하지 않았습니다.


## 2026-11-01 실행 결과

규칙 커밋: `5400a062489b64e5df5cf32541f47e2eaa3eaff4`, `pm-selection-v2`. [출처별 실제 관찰 범위](../data/collection/2026-11-01.json). 이전 기록과 정정은 보존합니다.

- 새 selected 사건 0건. 빈 상세 보고서와 알림을 만들지 않습니다. Chrome Releases 겹침 구간 16개 본문, Enterprise 156/157의 55개 항목, ChromeStatus 156–158의 58개 그룹 항목은 기존과 동일합니다. ChromeStatus 개별 출시 이력은 여전히 부분 확인입니다.
- Edge Stable 156.0.4314.58·Mobile 156.0.4314.43, Firefox 159 Desktop/Android·160 Beta를 재확인했습니다. 기존 Edge 신규성 정정과 Mobile 업무·학교 계정 범위를 유지합니다. Firefox note ID 52개와 개발자 참조 3개는 기존 55개 색인과 일치하며, 본문 hash는 향후 비교용으로 저장했습니다.
- Brave 최근 7일의 29개 릴리스가 이전 관찰과 동일합니다. Android 최신 변경 상세는 미확인입니다. Whale 공식 공지의 최신 발표는 10/1이며, 공개 제품 locale 자산에서 안내 15개를 baseline으로 복구했지만 실제 화면·출시 시점·플랫폼 범위는 미확인으로 남겼습니다.
- Opera·Vivaldi 5개 주간 출처는 아직 예정 전이므로 재수집하지 않았습니다. 이를 성공이나 변화 없음으로 기록하지 않았습니다.
- Chrome 최신 소스 commit 2개를 수집했습니다. Android GPU sandbox 등록은 보안 격리 실험이며 Glic 인쇄 flag 제거는 이미 기본 활성화된 gate 정리입니다. 둘 다 제품 출시·철회로 간주하지 않습니다. about_flags 2개 diff replay 결과가 공식 종료 snapshot과 일치합니다. 원래 1,169개 commit archive는 변경하지 않았습니다.
- metadata 6/9–15의 51개 diff, 설명 후속 헤더 6/1의 4개 diff를 보완했습니다. 다음 재개는 각각 6/16·6/2 00:00 UTC입니다. 나머지 역사 구간과 flag 연결 미완료를 유지합니다.
- Google 한국 RSS·본문을 확인했고 Microsoft 한국 아카이브는 부분 확인입니다. 기존 관심 기능 지원조건의 주간 점검은 예정 전입니다. 모든 설치본·한국 단말·벤치마크 실기는 미실행입니다.


## 2026-11-02 실행 결과

규칙 커밋: `31dafe16e8d748c8c55da33e63ed4a56e74b6acf`, `pm-selection-v2`. [출처별 실제 관찰 범위](../data/collection/2026-11-02.json). 기존 내용과 정정 이력을 보존합니다.

- 새 selected 사건 0건. 상세 보고서·메일은 만들지 않습니다. Chrome Releases 16개, Enterprise 156/157의 55개 항목과 Chrome·한국 블로그는 기존과 동일합니다.
- ChromeStatus 158 목록은 21→20개로 변경됐지만 SVG textPath side 개별 API는 존속하며 Proposed·shipping milestone null입니다. [목록 누락 사건](../data/events/chrome-svg-textpath-side-list-omission-20261102.json)을 검증 대기로 보존하며 기능 철회·출시로 간주하지 않습니다. 현재 156–158 목록 총 57개와 누락 항목을 함께 보관합니다.
- Edge·Firefox 14개 출처와 기존 145개 항목을 재확인했습니다. 직접 수집 10개 본문 hash는 직전과 동일합니다. Edge 신규성 정정·Mobile 업무/학교 계정 조건·Firefox Beta와 Stable 구분을 유지합니다. Microsoft 한국 아카이브는 부분 확인입니다.
- Brave 겹침 29개 릴리스 본문·제목·게시일·채널과 Whale 공식 운영팀 발표·제품 locale 문구는 기존과 동일합니다. Brave Android 최신 상세 및 Whale 실제 제품 화면·출시 조건은 미확인입니다.
- Opera·Vivaldi 5개 주간 출처와 기존 한국 지원조건·P1/P2 적정성 검토는 예정 전으로 생략했습니다. 성공 또는 변화 없음으로 기록하지 않습니다.
- Chrome 최신 3파일 이력은 직전 성공 이후 새 commit 0개이며 about_flags 공식 snapshot 동일을 확인했습니다. metadata 6/16–22의 39개 diff, 후속 설명 헤더 6/2–8의 42개 diff를 보완했습니다. 다음 재개는 각각 6/23·6/9 00:00 UTC입니다. 원래 1,169개 commit archive는 변경하지 않았습니다.
- canonical Gitiles의 일부 일시적 502/503·시간 초과는 공식 Chromium GitHub mirror의 전체 patch로 보완하고 파일별 추가·삭제 줄 수를 확인했습니다. 출처 경로와 hash를 기록했으며 나머지 과거 이력·개별 flag 연결은 미완료입니다. 모든 설치본·한국 단말·실제 벤치마크는 미실행입니다.

## 2026-11-03 Whale 수집 누락 보완

기준 commit `5c956bc38d99fcc42da022924320029e800bb6d2`. [전체 항목 색인](../releases/whale/README.md#2026-11-03-전체-항목-보완)과 [검증 절차](whale-collection.md)를 추가했습니다.

정정: 앞선 “Whale 최신 발표 10/1” 및 “기존과 동일”은 당시 연구소·정적 제품 문구 범위에 한정됩니다. 홈페이지 별도 업데이트 게시판은 미포함이었으므로 Whale 전체 발표에 일반화할 수 없습니다. Android 4.1 등록일은 11/2이며 시각 미공개로 아침 실행 당시 누락을 단정하지 않습니다.

Desktop 27개와 Android 4.0 13개를 과거 보완하고 Android 4.1 4개를 신규 출처 관찰로 저장했습니다. 기존 파일은 보존합니다. 개별 본문은 전체 최상위 항목을 대조했으나 게시판 전체 과거/플랫폼별 범위와 제품 소개 본문은 partial입니다. iOS 기존 예고·제품 소개·연구소 전체 checkpoint를 이번 단일 본문 확인으로 전진시키지 않습니다. 새 selected 0건, 상세 보고·메일·일정 변경 없음. Android 4.1의 신규성·이전 전달 대조가 남아 있습니다.

기존 Whale 수집 스크립트·CI는 없었습니다. 항목 검증기와 회귀 테스트 8개를 추가해 실행했고 3개 본문 색인의 44개 항목 검증을 통과했습니다. 실제 브라우저 제품 동작 테스트는 미실행입니다.


## 2026-11-03 실행 결과

규칙 커밋: `c2bfde4b1d3aeaef29b44302753c9f9981d3c867`, `pm-selection-v2`. [출처별 실제 범위](../data/collection/2026-11-03.json).

- Whale Android 4.1 설정 검색(한글 초성·문장 질의)과 시크릿 캡처·녹화 허용 옵션 2개를 신규성 대조 후 선정했습니다. [상세 분석](../reports/2026-11-03.md). 등록 11/2·본문 배포 10/29·관찰 시각을 분리했고 한국 제공 및 설치본 동작은 미확인입니다. 원래 보완 수집의 pending 판정 이력은 보존했습니다.
- Whale 홈페이지 공식 공지 전체 및 Desktop(categoryId=99)·iOS(100)·Android(101) 탭을 실제 UI로 확인했습니다. 각 첫 페이지가 최근 7일 경계를 덮고, 기간 내 Android 4.1 한·영 원문은 고유 4개 항목으로 대조했습니다. 공지의 현재 구간 확인 성공은 전체 과거 이력 완료가 아닙니다. 연구소 본문은 정규화 텍스트 동일. 제품 소개 텍스트 렌더링을 확인했지만 영상 재생과 기능별 적용 조건은 미확인으로 별도 partial 유지합니다.
- Chrome Releases 16개와 블로그 본문은 동일. Enterprise Gemini 목록 누락·GPC 목록 누락은 검증 대기, scroll snap 159 계획은 watch이며 출시·철회로 단정하지 않습니다. WebHID 재수록과 수정 시각은 신규 사건이 아닙니다. 기존 SVG 미확인 이력도 보존합니다.
- Edge Mobile 156.0.4314.56(11/2)은 일반·보안 수정으로 수집만 합니다. WebView2 디렉터리 검사 예고의 두 문서 누락은 pending입니다. Firefox 6개 본문 hash 동일. Microsoft 한국 홈의 10/29 새 기사 본문은 브라우저 기능이 아니며 전체 아카이브는 여전히 partial입니다.
- Brave Beta/Nightly artifact-only 신규 5개를 수집했습니다. Android 1.98.60의 공식 릴리스 노트 날짜 10/27 근거 보완은 과거 GitHub 게시일과 분리해 정정·검증 대기로 보존합니다. Android 최신 상세와 latest 채널 시차는 partial이며 desktop 내용을 Android 도입 근거로 삼지 않습니다.
- Chrome 소스 최신 고유 5개 commit을 확인하고 about_flags 3 diff를 재적용해 공식 종료 snapshot과 일치함을 확인했습니다. MagiChrome 실험 정리는 watch, 나머지는 수집·제외입니다. metadata 6/23–29의 47 diff, header 6/9–15의 36 diff를 보완했습니다. 재개는 각각 6/30·6/16. 원래 1,169 commit archive와 소스/실기 구분은 유지합니다.
- Opera·Vivaldi 5개 주간 출처와 기존 한국 지원 조건·P1/P2 검토는 예정 전으로 생략했습니다. 성공·변화 없음으로 표시하지 않습니다. 사내 자료 접근과 실제 벤치마크는 수행하지 않았습니다.

## 2026-11-04 실행 결과

규칙 commit `35058584c0ab1b2b75b4dc8bf09dec550e8a2c5e` / pm-selection-v2. [출처별 실제 범위](../data/collection/2026-11-04.json), [선정 13건 분석](../reports/2026-11-04.md). 기존 정정·이력은 보존합니다.

- Whale 전체·Desktop·iOS·Android 목록의 최근 7일 구간과 해당 4개 한·영 본문, 연구소 신규 63213 원문을 읽었습니다. Desktop 5.41.429.2의 19항목을 별도 색인화하고 Android 4.1의 기존 사건은 반복 제외했습니다. 등록 11/3·본문 11/2 Beta를 구분하며 연구소 영어 Stable/Beta 상충을 보존합니다. 제품 소개 영상은 부분 확인입니다.
- Edge 신규 사기 알림 자동 권한 취소·차단 및 신고, Firefox 159.0.1 관련 사이트 간 패스키 로그인 수정은 구체적 사용자 행동 변화로 선별했습니다. 일반 패치·예고·문서 누락은 전체 색인에서 별도로 유지합니다.
- Chrome 새 157 Stable 3개 및 156 Extended Stable 공지는 빌드·보안·일반 수정으로 수집만 했습니다. SVG textPath 158 목록 복귀는 watch이며 기존 누락 사건을 지우지 않았습니다. GPC API 403, Enterprise Gemini 목록 누락의 미확인은 유지합니다.
- Brave 37개 겹침 구간 릴리스·50개 최신 본문 항목·Android 2개 참조를 색인화했습니다. 새 artifact-only 7개와 Android 1.98.63 엔진 수정은 selected 제외. 1.99.54의 Release 이름과 prerelease=true를 혼동하지 않습니다.
- Chrome 최신 고유 15개 commit의 파일별 13/11/8 diff, 과거 metadata 22개·설명 헤더 28개 diff를 검증했습니다. about_flags replay는 공식 828926d snapshot과 일치. 원래 1,169개 archive는 유지하고 과거 재개는 metadata 7/7·헤더 6/23 UTC입니다. 북마크바 키보드 구역 탐색은 소스 실험 P2, 설치본 미확인입니다.
- Opera·Vivaldi, 기존 한국 조건 주간 점검 및 P1/P2 적정성 검토는 기한 전입니다. 예정 전 생략을 성공·변화 없음으로 기록하지 않았고 기준·일정은 변경하지 않았습니다. 모든 직접 시험은 미실행입니다.

## 2026-11-04 KST Edge 알림 자동 해제 신규성 정정

- 사건: `edge-notification-scam-auto-revocation-156`. Edge 152.0.4191.53(2026-08-27) 공식 Stable 노트에 SmartScreen 탐지 연계 자동 해제·사용자 안내·설정 복구의 controlled rollout이 이미 명시되어 있다. 11/2 글의 156 설명과 단계 차이가 밝혀지지 않아 신규성 검증 대기로 정정한다. 156에서 Scareware 경로가 최초 추가됐다고 단정하지 않는다.
- [152 공식 근거](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-archive-stable-channel#version-1520419153-august-27-2026-stable---main-release) · [정정 분석](../reports/2026-11-04.md) · [사건 이력](../data/events/edge-notification-scam-auto-revocation-156.json).
- 최초 게시의 selected 13건에서 해당 1건을 `pending_verification`으로 전환하여 현행 selected는 12건이다. 기존 선정·P1 사유와 관찰 시각은 정정 이력으로 보존했다.
- 156의 최초 도입·Scareware 최초 추가·배포 확대를 단정하지 않으며 신규 출시로 재알림하지 않는다. 실기·한국 제공은 여전히 미확인이다. 정정은 수집 checkpoint 전진이나 새로운 수집 성공을 뜻하지 않는다.

## 2026-11-05 실행 결과

규칙 commit `4663962fcdf1abddd0753e783a9fc5cd26a71007` / `pm-selection-v2`. [출처별 실제 범위](../data/collection/2026-11-05.json). 기존 기록과 Edge 신규성 정정을 보존합니다.

- 확인한 범위에서 새 selected 사건은 0건입니다. 실패·부분 수집 범위에 변화가 없었다는 뜻은 아니며 빈 상세 보고서는 만들지 않습니다.
- [Chrome 158 빌드 공지 4개](../releases/chrome/collection-2026-11-05.json)를 저장했습니다. Windows 소수 대상 Early Stable과 Desktop·Android·iOS Beta를 구분합니다. 개별 기능 변경이 명시되지 않은 빌드 참조로 수집만 했으며 Mac Early Stable은 예정입니다. 전체 feed·Git log·10월 겹침 구간은 미완료입니다.
- Chrome Enterprise는 API 접근 실패와 새 UI shell로 본문 재확인에 실패했습니다. ChromeStatus는 HTML 일부만 확인했고 Chrome Blog·Google 한국은 RSS/XML 및 본문 접근 제약으로 partial입니다. Chrome flags 현재 3개 소스는 확인했으나 이전 revision·변경 로그를 확보하지 못해 증분 diff·replay·과거 backfill은 미완료입니다. 기존 manifest와 1,169 commit archive는 변경하지 않습니다.
- Firefox Desktop 159.0.1의 9항목·Android 5항목, 160 Beta 및 MDN 159/160은 기존 수집과 의미상 같은 구성을 확인했습니다. 정규화 hash 전체 비교는 하지 않았으며 패스키 등 기존 사건을 재선정하지 않습니다.
- Edge Stable·보안·개발자 블로그·site-impacting 본문은 기존 근거와 의미상 중복입니다. Mobile Stable 직접 본문은 이번에 미조회했으며 보안 문서의 모바일 항목이 이를 대체하지 않습니다. Microsoft 한국 홈과 전체보기는 최근 기간 전체 확인이 안 되어 partial입니다.
- [Brave 신규 아티팩트 6개](../releases/brave/collection-2026-11-05.json)를 수집했습니다. Nightly 1.101.22–25, Beta 1.100.48, Release 표제 1.99.55이며 개별 기능 노트가 없어 상세보고에서는 제외합니다. API prerelease와 표제 채널을 따로 보존합니다. 최근 7일 전체 API 목록·수정 본문 비교는 두 차례 전송 실패로 partial입니다. latest의 Android 1.98.63 노출은 기존 changelog/API 사건과 같아 재선정하지 않습니다.
- [Whale 공식 API 목록·4개 한영 본문 및 연구소 재확인](../releases/whale/collection-2026-11-05.json)은 최근 7일 구간을 덮었습니다. 기존 Desktop 19항목·Android 4항목을 기존 색인과 대조했으며 새 원문은 없습니다. 홈페이지 한영 공지는 모두 Beta이고 연구소 영어의 Stable/Beta 상충은 보존합니다. 제품 소개는 JS shell로 partial이며 전체 과거 이력·제품 기능 검증 완료를 주장하지 않습니다.
- Opera·Vivaldi 정규 주간 수집, 기존 관심 기능의 한국 지원 조건 및 P1/P2 재검토는 예정 전입니다. 예정 외 참고 조회가 있더라도 정규 주간 수집 성공으로 처리하지 않습니다. 모든 설치본·한국 단말·직접 벤치마크는 미실행입니다.


예정 외 참고: Opera Desktop 139 Stable·140 Developer 및 Vivaldi 8.2 minor update·8.3 RC 공지를 보조 조회했습니다. [참고 URL과 한계](../data/collection/2026-11-05.json)에 남기며 이번 정규 주간 완료나 신규 selected 판정으로 집계하지 않습니다.


## 2026-11-06 실행 결과

규칙 commit `d1b38c7d605bff79d5526cfcc01729fc71d1bab5` / `pm-selection-v2`. [출처별 범위](../data/collection/2026-11-06.json), [상세 분석](../reports/2026-11-06.md), [전체 생성 기록](../reports/run-history.md).

- 확인 범위에서 신규 selected 17건. Vivaldi 8.3의 정식 포함·동작 변화 10건, Opera 창별 세로 탭 상태 1건, Brave 정식 채널 3건, Edge 새 탭 1건, Chrome 소스 실험 2건입니다. 기존 기능의 최초 출시로 확대하지 않습니다.
- Chrome Releases 21개 본문, Enterprise 88개 그룹/41개 고유 항목, ChromeStatus 75개 그룹/70개 고유 항목을 확인했습니다. 목록 재등장·milestone 이동은 출시·철회로 세지 않습니다. Firefox 기존 노트와 MDN을 대조했고 PiP 반복 note는 재선정하지 않았습니다.
- Brave 48개 겹침 릴리스와 1.99.55 기능별 정식 노트를 확보했습니다. 이전 artifact-only 수집과 날짜·채널을 분리했고 Android에 Desktop 기능을 일반화하지 않았습니다.
- Whale 최근 구간 목록·본문은 기존과 같으며 제품 소개는 부분 확인입니다. Vivaldi Stable Desktop 111개·Android 74개 변경 항목, Opera 31개 changelog 항목을 보조 관찰 범위에 보존했습니다.
- 기존 한국 지원 기준선 5개와 과거 관심 기능 7개를 재확인·보완했습니다. 새로운 한국 제공 사건은 0건이며 한국어 Smart Window 본문 실패는 유지합니다. P1/P2 검토는 기한 전이며 등급 기준은 바꾸지 않았습니다.
- 모든 설치본·실기 벤치마크는 미실행입니다. 전체 과거 수집·한국 제공 검증 완료를 주장하지 않습니다.

Chrome 소스 최신 고유 23개 commit을 수집했습니다. about_flags 21·metadata 19·설명 후속 헤더 16 diff 모두 직전 snapshot부터 재적용하여 공식 종료 8b41794e snapshot과 일치했습니다. 10/27부터의 겹침 78/77/60개 이력도 직전 성공 색인과 대조했습니다. 과거 metadata 7/7–13의 40개·헤더 6/23–29의 33개 diff도 각각 공식 endpoint snapshot replay를 검증했습니다. 재개는 metadata 7/14·헤더 6/30 UTC입니다. 원래 1,169개 archive는 유지합니다. descriptions.cc는 요청기간 이전에 삭제된 경로로 재확인했으며 현재 이력 0건을 접근 실패로 처리하지 않습니다. 소스 실험 P2 2건, watch 14건, excluded 7건이며 모든 설치본·한국 조건·실기 시험은 미확인/미실행입니다.

## 2026-11-07 실행 결과

규칙 commit `3740f5c80e1c14f191bbd4ea4357db9fcbd750d4` / `pm-selection-v2`. [출처별 범위](../data/collection/2026-11-07.json), [상세 보고서](../reports/2026-11-07.md), [전체 기록](../reports/run-history.md). 이전 기록과 Edge 신규성 정정을 보존합니다.

- 확인 범위 신규 selected 15건. Whale 기존 Beta 기능 9건의 Stable 포함, 주소창 AI 질의 전송·캡처·Windows 웹 앱 다중모니터 수정 3건, Edge 157 두 변화와 Chrome 소스 실험 한 건입니다. 공식 노트 수록과 실제 설치본 제공을 구분합니다.
- Whale 홈페이지 같은 URL의 .2→.3 본문 갱신에서 최초 등록 11/3·현재 본문 배포 11/6·관찰일을 구분했습니다. 한·영 홈페이지와 운영팀의 Stable/Beta 표기가 일치하며 .2 당시 19개 색인·상충은 보존합니다. 현재 28개 최상위 항목(개선 18·수정 10)을 모두 색인화했습니다.
- Chrome Releases 16개 겹침 공지와 새 빌드 참조 3개, Enterprise 88개 그룹/41개 기능, ChromeStatus 75개 그룹/70개 기능을 확인했습니다. Android 실제 배포와 Desktop 보안 참조 버전, 플랫폼별 예정·배포를 분리했습니다. Enterprise 및 Status 현재 본문·단계는 직전과 동일하며 전체 과거 이력 완료는 아닙니다.
- Edge 157의 OneAuth 완료와 탭 hover 메모리 정보·설정 분리를 선정했습니다. Apple 로그인·fading 제거는 152/153 선행 근거로 새 도입에서 제외하고 Copilot 등 단계 차이 미확인은 보존했습니다. Firefox 70개 note 본문은 직전과 동일합니다.
- Brave 겹침 35개 릴리스 중 새 Nightly 4·Beta 1은 artifact 참조로 수집만 했습니다. Opera Mobile 주간 본문은 기존 여행 기능 활용 안내이며 새 기능으로 선정하지 않았습니다. 다른 Opera/Vivaldi 주간 출처는 예정 전입니다.
- 한국어 Smart Window 도움말 재시도는 실패했고 Microsoft 한국 최근 전체 아카이브·Whale 제품 소개는 부분 확인을 유지합니다. 정규 한국 지원 주간 점검과 P1/P2 적정성 검토는 예정 전이며 기준·일정은 변경하지 않았습니다.
- 모든 설치본·한국 단말·벤치마크 시험은 미실행입니다.

Chrome 소스 고유 신규 14커밋을 수집했다. about_flags 12·metadata 10·설명 헤더 9개 diff를 직전 snapshot부터 재생하여 공식 종료 d67aec7c와 byte-identical임을 확인했다. 10/29 22:47 UTC부터 최근 겹침 57/51/43개 이력은 직전 색인과 정확히 일치했다. metadata 7/14–20 40개·header 6/30–7/6 18개도 전체 재생 검증했다. 재개는 metadata 7/21, header 7/7 UTC이다. 원본 1,169개 archive와 retired descriptions.cc의 과거 삭제 증거를 유지했다. 신규 selected 1·watch 7·excluded 6. 한국·설치본·실기는 미확인이다. 전체 과거 파일 이력은 여전히 부분 완료다.

