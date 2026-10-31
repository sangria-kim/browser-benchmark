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
