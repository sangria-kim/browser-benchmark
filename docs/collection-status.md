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
