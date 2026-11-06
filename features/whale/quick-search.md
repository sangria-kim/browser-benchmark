# 퀵서치

- browser: whale
- canonical feature key: `quick-search`
- feature_id: `whale-quick-search`

## 기존 기능과의 관계

5.39.412.57은 선택문을 AI Chat으로 보내는 흐름을 설명했다. 이번 사건은 퀵서치 내 NAVER AI 브리핑 경로이며, 기존 AI Chat·AI 브리핑 서비스 자체의 최초 출시로 세지 않는다.

기존 퀵서치 도움말의 전체 사용·검색 서비스 선택과 구별되는 결과 유형 단위 제어다. AI 브리핑 토글이 반드시 포함된다는 근거는 없다.

날짜 없는 제품 소개의 유사 AI 브리핑 문구는 기존 baseline으로 보존합니다. 이번 사건은 버전·Beta 범위를 특정한 변경 근거이며 기능의 최초 제공일은 미확인입니다.

## 이력

- 2026-11-03: 공식 Desktop 공지 등록. 본문 Beta 날짜는 2026-11-02.
- 2026-11-04 KST: 공식 본문·기존 기록·도움말 대조 후 아래 동작 변화 선정. 실제 기기 시험은 미실행.
- 선택 텍스트의 NAVER AI 브리핑과 사이드바 검색 연결 · P2 · [사건](../../data/events/whale-desktop-quick-search-ai-briefing-5-41-429-2-20261102.json).
- 퀵서치 정답형 결과를 유형별로 표시 제어 · P2 · [사건](../../data/events/whale-desktop-quick-search-answer-toggles-5-41-429-2-20261102.json).

[19개 전체 항목](../../releases/whale/5.41.429.2/items-desktop-assessment-2026-11-04.json) · [상세 분석·시험 후보](../../reports/2026-11-04.md).

## 범위와 불확실성

홈페이지 한국어·영문 공지와 연구소 제목·한국어 본문은 Beta. 연구소 영문 본문의 Stable, Beta 표기는 상충하며 Stable 제공은 미확인.

Desktop Beta 5.41.429.2. 항목별 OS·국가·언어·구독·연령·단계 배포 조건은 미공개. 한국어 공지 존재만으로 한국 제공·한국어 기능 지원을 확정하지 않음. 실제 지원 OS는 미확인이며 Desktop을 Windows·macOS·Linux 전체 지원으로 확장하지 않습니다.

## 2026-11-07 관찰: Desktop 5.41.429.3

공식 본문의 배포 표기는 2026-11-06 Stable/Beta다. 동일 URL의 최초 등록일 11/3과 구분하며, .2 Beta의 기존 기록을 변경하지 않는다. 한국 제공·한국어 지원은 각각 미확인, 실기 미실행이다.

- [whale-desktop-quick-search-ai-briefing-5-41-429-3-stable-20261106](../../data/events/whale-desktop-quick-search-ai-briefing-5-41-429-3-stable-20261106.json): 기존 .2 Beta 기능의 소개는 반복이지만 .3의 공식 채널이 Stable/Beta로 일치해 정식 채널 포함을 확인. 실제 전체 설치본 활성화는 미검증.
  - P2: 읽던 문맥에서 검색 답변을 보는 탐색 경로의 제한적 개선이며 AI라는 이유만으로 P1을 부여하지 않음.
  - 비교 질문: 같은 글의 질문을 해결할 때 페이지·탭 전환 수와 원문 복귀 비용이 어떻게 달라지는가?
  - 검증: 같은 글의 동일 문장을 선택해 AI 브리핑을 읽고 더보기로 이동한 뒤 원문에 복귀한다. 결과 유형 설정을 각각 끄고 켠다.
  - 지표: 답변 노출, 페이지 전환 수, 스크롤 위치 유지, 설정별 노출 일치
  - 준비도: conditional. 5.41.429.3 Stable 설치본의 기능 노출·동작 및 OS·계정·한국 제공 조건 확인
- [whale-desktop-quick-search-answer-toggles-5-41-429-3-stable-20261106](../../data/events/whale-desktop-quick-search-answer-toggles-5-41-429-3-stable-20261106.json): 기존 .2 Beta 기능의 소개는 반복이지만 .3의 공식 채널이 Stable/Beta로 일치해 정식 채널 포함을 확인. 실제 전체 설치본 활성화는 미검증.
  - P2: 특정 검색 결과의 노출을 세부 조정하는 사용자 통제 개선.
  - 비교 질문: 필요한 즉답만 남길 때 설정 탐색 비용과 원치 않는 결과 노출이 얼마나 달라지는가?
  - 검증: 같은 글의 동일 문장을 선택해 AI 브리핑을 읽고 더보기로 이동한 뒤 원문에 복귀한다. 결과 유형 설정을 각각 끄고 켠다.
  - 지표: 답변 노출, 페이지 전환 수, 스크롤 위치 유지, 설정별 노출 일치
  - 준비도: conditional. 5.41.429.3 Stable 설치본의 기능 노출·동작 및 OS·계정·한국 제공 조건 확인

[공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)
