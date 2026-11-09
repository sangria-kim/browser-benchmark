# 공개 기능 자료 원칙

## 공개 대상

Chrome·Edge·Firefox·Brave·Whale·Opera·Vivaldi의 기능 설명, 사용자 영향, 공식 출처, 발표·적용 시점, 버전·채널·플랫폼, 지역·언어·계정·기기·구독 조건과 증거 수준을 기록합니다. 사내 자료나 내부 의사결정은 포함하지 않습니다.

공식 출처의 본문과 section, URL, 확인일, 소스 revision 또는 내용 hash를 근거로 유지합니다. 확인일과 출시일은 구분합니다. 소스 flag 등록·삭제는 출시나 철회의 단독 증거가 아닙니다. 릴리스 노트 수록을 모든 설치본 활성화로 일반화하지 않습니다.

## 기능 분석

[PM 분석 기준](pm-persona-and-selection.md)에 따라 사용자 과제, 실질적 변화, 비교 질문, 벤치마크 절차·지표를 설명합니다. 추측으로 제품 지원을 채우지 않습니다. 기능의 한국 제공·한국어 지원과 직접 동작 확인 여부가 불명확하면 unknown으로 남깁니다. 소스 관찰 / 설치본 노출 / 동작 검증의 증거 수준을 구분합니다.

기능 ID는 브라우저와 canonical feature key로 유지하고 사건 ID로 중복을 구분합니다. 기존 기능의 Beta→Stable 확대는 최초 도입과 구분합니다. 기능 사실의 정정은 근거와 함께 설명합니다.

## 운영 자료와 분리

조사 진행 범위·미확인 자료 목록·실행 시각표·수집 오류·재시도·checkpoint·보고 생성 여부·게시 결과·메일 상태·개인 식별자 및 운영 정정 원문은 비공개 Notion 일별 기록에 보관합니다. 이 저장소에 운영 로그나 비공개 기록 링크를 추가하지 않습니다. 운영 원문을 보존한 후 현재 공개 파일에서 제거하며 과거 Git 이력은 강제 재작성하지 않습니다.

## 기능 사건 필드

schema_version, event_id, feature_id, browser, event_type, version, channel, platform, workstreams, ai_related, scope, observed_at, announced_at, effective_at, source_revision, sources, summary, delta, verification_status, previous_event_id, selection_status, selection_reason, priority, priority_reason, comparison_question, benchmark_readiness, revisit_trigger, assessed_at, selection_rule_version.

scope는 제품 적용 조건이며 조사 완료율이 아닙니다. observed_at은 근거를 확인한 시점이며 실행 성공·발송 상태를 의미하지 않습니다. JSON의 null/unknown은 미확인 제품 정보나 증거 수준을 뜻합니다.
