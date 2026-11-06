# 첫 로그인 때 기존 환경 이어쓰기

- browser: whale
- canonical feature key: `sign-in-continuity`
- feature_id: `whale-sign-in-continuity`

## 기존 기능과의 관계

5.39.412.57의 로그인 관련 변경은 안내창 디자인·문구 통일이었다. 이번은 첫 로그인에서 사용 중인 환경을 이어가는 명시적 선택이다. 기존 모든 동기화 기능의 도입으로 일반화하지 않는다.

## 이력

- 2026-11-03: 공식 Desktop 공지 등록. 본문 Beta 날짜는 2026-11-02.
- 2026-11-04 KST: 공식 본문·기존 기록·도움말 대조 후 아래 동작 변화 선정. 실제 기기 시험은 미실행.
- 첫 로그인에서 기존 북마크·비밀번호·설정 이어쓰기 · P1 · [사건](../../data/events/whale-desktop-sign-in-continuity-5-41-429-2-20261102.json).

[19개 전체 항목](../../releases/whale/5.41.429.2/items-desktop-assessment-2026-11-04.json) · [상세 분석·시험 후보](../../reports/2026-11-04.md).

## 범위와 불확실성

홈페이지 한국어·영문 공지와 연구소 제목·한국어 본문은 Beta. 연구소 영문 본문의 Stable, Beta 표기는 상충하며 Stable 제공은 미확인.

Desktop Beta 5.41.429.2. 항목별 OS·국가·언어·구독·연령·단계 배포 조건은 미공개. 한국어 공지 존재만으로 한국 제공·한국어 기능 지원을 확정하지 않음. 실제 지원 OS는 미확인이며 Desktop을 Windows·macOS·Linux 전체 지원으로 확장하지 않습니다.

## 2026-11-07 관찰: Desktop 5.41.429.3

공식 본문의 배포 표기는 2026-11-06 Stable/Beta다. 동일 URL의 최초 등록일 11/3과 구분하며, .2 Beta의 기존 기록을 변경하지 않는다. 한국 제공·한국어 지원은 각각 미확인, 실기 미실행이다.

- [whale-desktop-sign-in-continuity-5-41-429-3-stable-20261106](../../data/events/whale-desktop-sign-in-continuity-5-41-429-3-stable-20261106.json): 기존 .2 Beta 기능의 소개는 반복이지만 .3의 공식 채널이 Stable/Beta로 일치해 정식 채널 포함을 확인. 실제 전체 설치본 활성화는 미검증.
  - P1: 첫 계정 로그인에서 비밀번호·북마크·설정의 귀속과 작업 연속성을 다루므로 보존·혼입·취소를 우선 검증할 필요가 있음.
  - 비교 질문: 로그인 전 환경을 계정에 연결할 때 데이터 보존·선택 명확성·계정 혼입 방지가 어떻게 다른가?
  - 검증: 비민감 테스트 북마크·비밀번호·설정을 만든 새 프로필에서 첫 로그인 및 이어쓰기를 수행한다.
  - 지표: 데이터 보존·중복·누락, 선택 의미 이해, 취소 시 상태
  - 준비도: conditional. 5.41.429.3 Stable 설치본의 기능 노출·동작 및 OS·계정·한국 제공 조건 확인

[공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)
