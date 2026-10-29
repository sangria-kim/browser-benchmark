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
