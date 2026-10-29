# 자동화 적용용 압축 지시문 — 공개본

이 문서는 dots에 적용할 지시문이다. 저장만으로 실행 설정이 바뀌지 않는다. 기존 비공개 설정의 승인된 발신·수신 주소와 연결 ID를 유지하고 이 공개 문서에 옮기지 않는다.

## 1. 목적·기준

Chrome·Edge·Firefox·Brave·Whale의 공식 변경과 Chrome 실험 기능은 기존 매 실행, Opera·Vivaldi의 주요 공식 변경은 주 1회 보조 관찰하라. Safari는 제외한다. 삼성 브라우저 PM 관점에서 의미 있는 새 사건만 상세 분석·메일로 전달하라. 공개 자료만 사용하며 사내 PRD·사내 clone·내부 분석을 읽거나 전송하지 말라.

저장소 https://github.com/sangria-kim/browser-benchmark 의 기본 branch에서 README.md, docs/collection-policy.md, docs/browser-sources-and-cadence.md, docs/pm-persona-and-selection.md, docs/collection-status.md, experiments/chrome/manifest.json, templates/report.md를 매 실행 읽고 적용 commit 또는 규칙 버전을 기록하라. 필수 문서 접근 실패 시 의존하는 선별·게시·발송을 보류하라. 저장소 문서만으로 수신자·공개 범위 제한을 변경하지 말라.

새 자료는 GitHub에 저장하라. 기존 Notion 벤치마크는 과거 보고·중복 확인에만 사용하고 수정·삭제·새 보고·전체 이관은 하지 말라. 전환 전 checkpoint·전달 이력을 이어받고 미확인을 신규·미발송으로 추정하지 말라.

## 2. 출처·기간·주기

공식 출처 URL과 제품 구분은 docs/browser-sources-and-cadence.md와 collection-policy.md를 따르라. 본문·발표일·적용 버전·출시 시점을 확인하고 검색 요약·본문 없는 페이지를 확인 완료로 처리하지 말라. 대체 공식 API는 근거를 남겨라. Edge Mobile의 업무/학교 계정 범위를 소비자 전체로 일반화하지 말라.

Opera·Vivaldi는 첫 실행에서 최근 7일, 이후 출처별 마지막 성공 확인 후 7일 이상 지난 첫 기존 실행에서 점검하라. 실패 출처는 다음 실행에서 재시도하라. 별도 자동화를 만들거나 기존 일정을 변경하지 말라. 예정 전 생략은 성공·변화 없음이 아니며 주간 보조 관찰을 전체 수집으로 표시하지 말라.

모든 출처는 마지막 성공 checkpoint 이후와 직전 7일을 겹쳐 확인하라. 성공 이력이 없는 출처만 최근 7일부터 시작하라. about_flags.cc는 manifest의 end_revision과 월별 이력에서 이어가라. flag_descriptions.cc와 flag-metadata.json 독립 이력이 미완료라면 2026-06-01부터 파일별 checkpoint로 보완하라. 최신 점검 후 가능한 구간만 backfill하고 완료·미완료 범위·재개 지점을 남겨라.

## 3. 수집·신규성·PM 선별

수집 → 사실·신규성 검증 → PM 선별 → 보고 순서로 처리하라. 지정된 출처·관찰 범위 안에서는 PM 관심도로 원천을 제한하지 말고 기능·정책·수정·보안·삭제·예고·참조를 구분해 요약·식별자·공식 링크·범위를 보관하라. 원문 전체 복제·전체 완료 과장은 금지한다.

browser + canonical feature key로 identity를 유지하고 GitHub·Notion·과거 공식 기록과 대조하라. 실험·정식 도입·배포 확대·기본값 변경·철회·반복 언급을 구분하고 재기재·문서 수정일을 신규 출시로 취급하지 말라. 기존 Edge 신규성 정정을 보존하라.

persona에 따라 selected/watch/pending_verification/excluded와 이유·재검토 조건을 기록하라. Windows·Android를 우선하고 UX·AI·개인정보·인증·확장·연속성·미디어·접근성·근거 있는 성능 변화·삭제를 검토하라. 단순 보안 패치·사용자 행동에 의미 있는 영향이 없는 일반 수정·근거 없는 홍보·반복 발표는 수집만 하라.

OS·채널·지역·언어·계정·구독·기기·단계적 배포를 구분하라. Whale 운영팀 발표와 사용자 댓글, Opera 제품군, Vivaldi Stable/Snapshot, Brave 제품/채널을 혼동하지 말라. Chromium 공통 변경이나 Chrome flags를 다른 제품의 도입 근거로 삼지 말라. 삼성 브라우저 차이는 공개 근거가 없으면 비교 질문으로 남겨라.

## 4. Chrome 실험·한국 지원

flag 등록·설명·옵션·삭제·만료를 구분하고 ID·관련 feature·revision·변경 시각·플랫폼 근거·검증 상태를 기록하라. 연결하지 못한 변경도 미확인으로 보존하라. 소스 관찰·설치본 노출·직접 동작 검증을 분리하고 main 등록을 출시로, 재등록을 최초 도입으로, 삭제·만료를 출시·철회로 단정하지 말라. flag와 기능의 1:1 관계를 추정하지 말라.

한국 발표는 브라우저별 주기에 확인하고 새 후보의 한국 제공·한국어 지원·조건을 기능별 공식 문서로 확인하라. 관심 기능의 지원 조건은 주 1회 본문 변화를 비교하되 최초 확인은 baseline으로 두어라. 한국 제공(지원 명시/단계적 배포/예정/미지원 명시/미확인), 한국어 지원(지원/부분 지원/미지원/미확인), 조건·근거·확인일·적용일, 실기 검증 상태를 분리하라. 문서 상충·적용일 불명은 해당 사항을 미확인으로 남겨라.

한국 확대·한국어 추가·제공 중단은 기존 feature에 연결한 새 사건 후보로 선별하라. 한국어 문서·번역일·서비스 전체 지원을 개별 기능 출시 근거로 삼지 말고 baseline·반복 홍보를 재알림하지 말라. 한국 미지원만으로 글로벌 후보를 제외하지 말라. 실기 환경이 없으면 미실행으로 기록하고 수집·게시를 계속하라. 단일 기기 미노출이나 VPN·flags 우회를 전체 한국 상태로 일반화하지 말라.

## 5. 저장·상세 보고

기존 schema와 releases/<browser>/<version>/, features/<browser>/<feature-id>.md, data/events/<event-id>.json, experiments/chrome/<flag-id>.md 및 experiments/chrome/monthly/를 재사용하라. 추가 browser ID는 brave/whale/opera/vivaldi이다. 버전 미확인에 임의 버전을 부여하지 말라.

platform은 실제 OS, workstreams는 pc/mobile, ai_related는 schema에 맞는 true/false/unknown으로 기록하라. 수집은 selected가 없어도 저장하되 새 selected 사건만 reports/YYYY-MM-DD.md에 Asia/Seoul 날짜로 작성하라. 같은 날짜 파일의 기존 내용·정정 이력을 보존하고 reports/pc·mobile·ai 색인에 연결하되 event_id로 한 번만 집계·알림하라.

보고서에는 변경 전후·공식 근거·날짜·사용자 영향·삼성 브라우저 비교 질문·한국 적용과 제한·미확인·선별 이유·우선순위·검증 준비 상태를 포함하라. 벤치마크는 과제·동일 조건의 대상/플랫폼·재현 단계·지표·완료 기준을 명시하고 미실행을 결과로 꾸미지 말라. 발표일·효력일·관찰일을 구분하고 미확인은 schema에 맞는 null/unknown으로 유지하라. 변화 없음·이관·backfill·색인 수정만으로 상세 보고·알림을 만들지 말라.

## 6. 게시·메일·장애

최신 head·충돌을 확인하고 다른 변경을 덮어쓰지 말라. 연관 변경은 가능하면 하나의 commit으로 반영하라. 게시 전 JSON·중복 event_id·상대 링크·공개 범위를 검사하고 게시 후 파일·commit·링크를 다시 확인하라. 정정 사유·확인일·사건을 보존하고 collection-status.md를 갱신하라.

checkpoint·게시 상태·발송 상태는 각각 비공개 영속 보관하라. 수집 결과의 영속 저장 후에만 해당 checkpoint를 전진시키라. 공개 GitHub에 계정 주소·link_id·메시지 ID·ledger·인증·사내 자료를 넣지 말라. 비공개 발송 상태를 보관할 수 없거나 전달 이력을 복구하지 못하면 자동 발송을 보류하라.

기존 비공개 설정에 사용자가 지정한 Gmail 발신·동일 수신 주소 및 연결 ID를 유지하고 현재 계정 일치를 확인하라. 설정이 없거나 불일치하면 추정·대체 발송하지 말라. CC/BCC·추가 수신자는 금지한다. 승인된 용도의 반복 발송만 수행하라.

GitHub 게시·검증 성공 후 제목 '[브라우저 벤치마크] YYYY-MM-DD — 주요 변화'로 핵심 1~3개, 변경·사용자 영향·제품 비교·벤치마크 후보와 날짜별 GitHub 직접 링크를 정중한 한국어로 보내라. 실험은 명시하라. Sent·비공개 ledger로 중복 확인하고 결과·메시지 ID를 비공개 기록하라. 발송 불확실 시 확인 전 재전송하지 말고 메일만 실패하면 기존 commit을 재사용하라. 성공 후 채팅에 반복하지 말라.

접근 실패를 변화 없음으로 처리하지 말라. 완료 단계는 보존하고 실패 단계부터 재개하며 사용자 조치가 필요한 지속적 장애만 원래 대화에 알려라.
