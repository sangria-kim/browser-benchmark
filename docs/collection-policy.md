# 수집 및 게시 지침

이 문서는 dots 작업에 반영할 운영 명세입니다. 문서 저장만으로 자동화 설정이 변경되지는 않습니다.

## 범위와 출처

Chrome, Edge, Firefox의 새 기능과 주요 동작 변경을 공식 자료에서 확인한다. Windows와 Android를 우선한다. 공개 제품 정보만 사용하며 사내 데이터를 읽거나 전송하지 않는다.

- Chrome: https://chromereleases.googleblog.com/ · https://blog.google/products-and-platforms/products/chrome/ · https://chromeenterprise.google/intl/en_en/resources/release-notes/ · https://chromestatus.com/release-notes
- Edge: https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-stable-channel · https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-mobile-stable-channel · https://blogs.windows.com/msedgedev/ 및 공식 site-impacting changes 문서
- Firefox: https://www.firefox.com/en-US/firefox/notes/ · https://www.firefox.com/en-US/firefox/android/notes/ · https://www.firefox.com/en-US/releases/ 및 MDN 개발자 릴리스 노트
- Chrome flags: https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/about_flags.cc · https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/flag_descriptions.cc · https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/flag-metadata.json 및 해당 파일 변경 이력

검색 요약이 아니라 본문·발표일·적용 버전·실제 출시 시점을 확인한다. Chrome Enterprise 본문이 로드되지 않으면 미확인으로 남긴다. Edge 모바일 문서의 업무/학교 계정 범위를 소비자 Android 전체로 일반화하지 않는다.

## Chrome 실험 기능

flag 추가·설명 및 옵션 변경·삭제·만료 변경을 직전 성공 snapshot과 비교한다. 최초 실행은 현재 목록을 baseline으로 기록하고 기존 flags 전체를 신규로 발표하지 않는다. 최근 변경 이력에서 확인된 사건만 새 관찰로 다룬다.

flag ID, 관련 feature ID, 소스 revision, 최초 관찰일, 플랫폼, 설명, 활성화 방법과 근거를 기록한다. 소스 main에서 발견한 사실과 실제 Canary/Dev/Beta/Stable 설치본 노출은 분리한다. 빌드 확인 없이 소스 변경을 특정 Chrome 버전 출시로 단정하지 않는다.

상태는 소스 관찰 / 설치본 확인 / 직접 동작 검증으로 구분한다. flag 만료·삭제는 출시 또는 기능 철회의 증거가 아니다. 모든 예정 기능에 flag가 있거나 실험 기능이 반드시 출시된다고 가정하지 않는다. 설명이 부족하면 추측 대신 미확인으로 기록한다.

## 수집·판정·중복 방지

첫 실행은 최근 7일, 이후 마지막 성공 점검 이후를 확인하며 이전 7일도 겹쳐 확인한다. 실패한 출처의 checkpoint는 전진시키지 않는다. 접근 실패와 변화 없음을 구분하고 실패 범위·재시도 대상을 비공개 실행 상태에 기록한다.

탭·탐색 UX, AI 작업 흐름, 개인정보 기본값, 인증·자동완성, 확장 기능, 기기간 연속성, 미디어, 접근성, 근거 있는 성능 변화와 기능 삭제를 우선한다. 보안 패치·일반 버그 수정·내용 없는 성능 홍보·반복 발표는 상세 보고와 알림에서 제외한다.

기능 identity는 browser + canonical feature key로 유지하고 버전·URL·번역명이 달라도 같은 기능 이력을 연결한다. flag와 제품 기능은 근거가 있을 때 연결하며 한 flag와 한 기능의 1:1 대응을 가정하지 않는다.

사건은 실험 관찰 / 정식 도입 / 배포 확대 / 동작 변경 / 철회 / 반복 언급 / 검증 대기로 구분한다. event ID와 browser, version, channel, platform, scope, delta를 기준으로 중복 제거한다. 근거 URL·section·확인 시각·소스 revision 또는 hash를 남긴다. 이미 전달한 사건을 다시 알리지 않는다.

Stable/실험/Beta/예고, 지역·언어·계정·기기 제한과 단계적 배포를 명시한다. 릴리스 노트 수록과 모든 설치본 활성화를 구분한다. 과거 공식 이력을 대조하며 재기재를 신규 기능으로 세지 않는다. 미확인 값은 null 또는 unknown으로 유지한다. 삼성 브라우저의 동등 기능·차이는 근거가 없으면 비교 질문으로 남긴다.

## 삼성 브라우저 PM 관점의 선별

### 역할과 적용 단계

삼성 브라우저 PM 관점에서 공개된 경쟁 브라우저의 변화를 평가한다. PC·Mobile·AI 업무 영역에서 사용자의 탐색·입력·멀티태스킹·작업 완료 방식이 어떻게 달라지는지 분석한다. 사용자 영향, 기존 기능 대비 실질적 변화, 재현 가능한 비교 과제가 있는 항목을 우선한다.

수집 → 사실·신규성 검증 → PM 선별 → 업무별 정리·보고 순서로 처리한다. 공식 자료의 변경은 폭넓게 탐지하며 PM 관점으로 수집 원천을 미리 차단하지 않는다. 선별은 상세 분석·알림 대상에 적용한다. 제외·보류 후보도 출처, 판정 이유, 재검토 조건을 수집 상태에 남겨 누락과 반복 검토를 방지한다. 일일 보고 건수를 채우기 위해 항목을 선정하지 않는다.

페르소나는 분석 관점이며 삼성의 내부 정보나 의사결정 권한을 뜻하지 않는다. 삼성 브라우저 지원 여부·차이·내부 로드맵·전략·개발 비용을 추정하지 않는다. 확인된 공개 근거가 없으면 비교 질문으로 남긴다. 경쟁사가 도입했다는 이유만으로 도입 필요·우열·차별화를 단정하지 않는다.

### 평가 기준

각 후보에 다음 질문을 적용하고 근거가 있는 짧은 이유를 기록한다. 임의의 점수 합계로 사실 검증을 대체하지 않는다.

| 기준 | 확인 질문 |
| --- | --- |
| 사용자 영향 | 어떤 사용자가 어떤 과제를 이전과 다르게 수행하는가? 조작·시간·오류·접근성·개인정보·호환성에 구체적인 영향이 있는가? |
| 실질적 변화 | 새 기능, 출시 단계, 지원 범위, 기본값, 동작 또는 기능 삭제에 명시적 변화가 있는가? 반복 발표·이름 변경과 구분되는가? |
| 제품 비교 가치 | 삼성 브라우저 검토에 연결할 사용자 과제와 비교 질문이 있는가? 지원 여부가 미확인이어도 확인할 질문이 구체적인가? |
| 벤치마크 가능성 | 동일 플랫폼·조건의 비교 대상, 재현 절차, 관찰·측정 지표와 완료 기준을 정의할 수 있는가? |
| 출시·검증 조건 | 실험/Beta/Stable 단계, 지역·언어·계정·기기 제한과 직접 확인 여부를 구분했는가? |

PC는 창·탭·키보드·사이드바·확장 기능·멀티태스킹, Mobile은 터치 탐색·모바일 탭·Android 동작·앱 간 연결, AI는 요약·정보 추출과 입력·감시·작업 자동화·데이터 전달과 사용자 통제를 중심으로 본다. 이는 우선 관찰 영역이며 새로운 사용자 과제를 배제하는 고정 목록이 아니다.

### 선별 결과와 우선순위

- **선정(selected)**: 공식 근거와 과거 이력 대조로 새로운 사건이 확인되고, 구체적인 사용자 영향·제품 비교 질문·검증 과제가 있다. 상세 보고 대상으로 삼고 중복 확인 후 알린다.
- **관찰(watch)**: 실험·예고 등 변화 자체와 제품 가치는 확인됐지만 시험 조건이나 접근성이 부족하다. 미확인 조건과 재검토 계기를 기록한다. 발표·소스 관찰 자체가 위 선정 요건을 충족하면 실험 후보로 선정할 수 있으나 실제 사용 가능·시험 완료로 표현하지 않는다.
- **검증 대기(pending_verification)**: 공식 근거 접근 실패, 출처 충돌, 신규성 불명확 등 사실 판정이 미완료다. 상세 신규 보고·자동 알림에서 제외하고 필요한 근거를 기록한다.
- **제외(excluded)**: 반복 발표, 단순 보안 패치·일반 수정, 근거 없는 성능 홍보 또는 구체적인 사용자 영향·비교 과제가 없는 항목이다. 제외 이유를 남기고 새로운 근거가 생기면 재검토한다.

선정된 항목의 P1은 기본 동작·개인정보·인증·기능 삭제처럼 기존 과제에 큰 영향을 주거나 핵심 과제의 변화를 우선 검증할 필요가 있는 경우, P2는 유용하지만 영향 범위가 제한적이거나 탐색적 비교가 필요한 경우로 구분한다. 각 우선순위에 이유를 붙인다. AI라는 이유만으로 P1을 부여하지 않으며, 국내 미출시도 제외 사유로 단정하지 않고 선행 검토 가치와 접근 제약을 함께 판단한다.

판정에는 selection_status, selection_reason, priority(P1/P2/null), priority_reason, comparison_question, benchmark_readiness(ready/conditional/unknown), revisit_trigger, assessed_at, selection_rule_version을 기록한다. 이 기준의 rule version은 pm-selection-v1이다. 과거 샘플을 새 기준으로 검토하지 않았다면 판정 완료로 표시하지 않는다.

## GitHub 게시

대상: https://github.com/sangria-kim/browser-benchmark 의 기본 branch.

PM 선별 결과가 selected인 의미 있는 새 사건이 있을 때만 reports/YYYY-MM-DD.md를 작성한다. 같은 날짜 문서가 있으면 기존 내용과 정정 이력을 보존하여 추가한다. 기능별 전체 이력, 브라우저/버전별 색인, JSON 사건 데이터를 함께 갱신한다. 버전 미확인 실험을 임의의 버전 폴더에 넣지 않는다. 변경이 없으면 빈 보고서를 만들지 않는다.

JSON 사건 필드: schema_version, event_id, feature_id, browser, event_type, version, channel, platform, workstreams, ai_related, scope, observed_at, announced_at, effective_at, source_revision, sources, summary, delta, verification_status, previous_event_id, selection_status, selection_reason, priority, priority_reason, comparison_question, benchmark_readiness, revisit_trigger, assessed_at, selection_rule_version. 날짜 의미를 혼용하지 않으며 미확인은 null로 둔다.

게시 후 파일을 다시 읽어 내용·상대 링크·commit을 확인한다. 충돌 시 최신 파일을 읽어 병합하며 다른 변경을 덮어쓰지 않는다. 보고서 commit 성공 전 전달 완료로 처리하지 않는다.

## 이메일과 비공개 실행 상태

기존 사용자가 승인한 발신·수신 계정을 실행 환경에서 확인하고 그대로 사용한다. 계정 주소와 link ID를 이 공개 저장소에 기록하지 않는다. 의미 있는 변화가 있을 때만 정중한 한국어로 핵심 1~3개를 요약하고 GitHub 날짜별 보고서 직접 링크를 제공한다. 제목은 '[브라우저 벤치마크] YYYY-MM-DD — 주요 변화'. CC/BCC 또는 다른 수신자를 추가하지 않는다.

변경·사용자 영향·제품 비교·벤치마크 후보를 간략히 담는다. 실험 후보는 실험임을 제목 또는 항목에 표시한다. Sent 및 비공개 발송 ledger를 확인하며 결과 불확실 시 재전송 전에 조회한다. event ID + 목적지 + 보고 종류로 중복 전송을 막는다. 메시지 ID·발송 결과·checkpoint는 비공개 환경에 보관한다. 게시 성공 후 메일만 실패하면 게시를 반복하지 않는다. 모두 성공하면 채팅에 중복 알림하지 않는다. 지속적인 사용자 조치 필요 장애만 알린다.

## 게시 안정화와 상태 관리

GitHub를 보고서의 기준 저장소로 사용한다. 이전에 전달한 사건은 비공개 발송 ledger와 대조하여 샘플 게시·색인 수정·문구 정리만으로 재알림하지 않는다. 최초 7일 수집 규칙은 새로운 수집 이력이 없는 경우에만 적용하고, 기존 성공 checkpoint가 있으면 이어서 처리한다.

수집 성공 checkpoint, GitHub 게시 상태, 메일 전달 상태를 별도로 관리한다. 수집 결과를 영속 보관하기 전에는 checkpoint를 전진시키지 않는다. GitHub 게시 실패 시 보류 사건을 유지해 재시도하고, 메일 실패 시 이미 게시된 commit을 재사용한다. 비공개 실행 상태를 잃었을 때는 전송 이력을 복구하기 전 자동 발송을 중지한다.

연관 보고서·색인·사건 데이터는 가능하면 하나의 commit으로 게시한다. 여러 commit이 필요한 실행은 미완료 상태를 비공개로 기록하고 모든 파일 검증 후에만 메일을 보낸다. branch 최신 head를 확인하고 충돌 시 최신 내용을 읽어 재적용한다. 정정은 기존 기록을 조용히 덮어쓰지 않고 사유·확인일·관련 사건을 남긴다.

운영 전 확인할 항목:

- 새 사건 1건이 날짜별 보고서와 버전 색인에 함께 저장되고 상대 링크로 열린다.
- 동일 입력 재실행과 동시 실행에서 사건·보고서·메일이 중복되지 않는다.
- 출처 실패, 게시 실패, 발송 결과 불확실 상황에서 완료된 단계만 보존해 복구한다.
- 변경 없음은 빈 보고서를 만들지 않고 비공개 점검 상태만 갱신한다.
- 공개 파일에 계정 주소·메시지 ID·인증 정보·사내 자료가 포함되지 않는다.
- 사내 환경에서 clone/pull 후 상대 링크를 따라 문서를 읽을 수 있다.

현재 샘플은 Markdown 보고서와 색인만 포함한다. JSON 사건 데이터·기능별 문서·flags snapshot과 위 운영 검증은 아직 완료되지 않았다. 메일·checkpoint 영속 저장 위치는 실제 실행 환경에서 마련하고 확인해야 한다.

## 업무 분류 원칙

PC/Mobile은 플랫폼, AI는 기능 속성으로 분리한다. platform에는 실제 OS를 기록하고 workstreams에는 pc/mobile, ai_related에는 true/false/unknown을 둔다. 같은 사건이 여러 업무 목록에 노출돼도 event_id 기준으로 한 번만 집계·알림한다. 실제 지원 범위가 미확인인 플랫폼을 임의로 추가하지 않는다. 업무별 색인은 현재 미구현이며 날짜별·버전별 색인을 사용한다.
