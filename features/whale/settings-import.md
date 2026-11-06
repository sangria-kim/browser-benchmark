# 단축키를 포함한 설정 가져오기

- browser: whale
- canonical feature key: `settings-import`
- feature_id: `whale-settings-import`

## 기존 기능과의 관계

공지에 Whale 원본에서 가져올 설정 범위의 확장이 명시된다. 다른 브라우저의 모든 설정 가져오기나 모든 OS 사이 호환으로 확대하지 않는다.

## 이력

- 2026-11-03: 공식 Desktop 공지 등록. 본문 Beta 날짜는 2026-11-02.
- 2026-11-04 KST: 공식 본문·기존 기록·도움말 대조 후 아래 동작 변화 선정. 실제 기기 시험은 미실행.
- Whale 가져오기에 단축키 포함 설정 전체 추가 · P2 · [사건](../../data/events/whale-desktop-settings-import-shortcuts-5-41-429-2-20261102.json).

[19개 전체 항목](../../releases/whale/5.41.429.2/items-desktop-assessment-2026-11-04.json) · [상세 분석·시험 후보](../../reports/2026-11-04.md).

## 범위와 불확실성

홈페이지 한국어·영문 공지와 연구소 제목·한국어 본문은 Beta. 연구소 영문 본문의 Stable, Beta 표기는 상충하며 Stable 제공은 미확인.

Desktop Beta 5.41.429.2. 항목별 OS·국가·언어·구독·연령·단계 배포 조건은 미공개. 한국어 공지 존재만으로 한국 제공·한국어 기능 지원을 확정하지 않음. 실제 지원 OS는 미확인이며 Desktop을 Windows·macOS·Linux 전체 지원으로 확장하지 않습니다.

## 2026-11-07 관찰: Desktop 5.41.429.3

공식 본문의 배포 표기는 2026-11-06 Stable/Beta다. 동일 URL의 최초 등록일 11/3과 구분하며, .2 Beta의 기존 기록을 변경하지 않는다. 한국 제공·한국어 지원은 각각 미확인, 실기 미실행이다.

- [whale-desktop-settings-import-shortcuts-5-41-429-3-stable-20261106](../../data/events/whale-desktop-settings-import-shortcuts-5-41-429-3-stable-20261106.json): 기존 .2 Beta 기능의 소개는 반복이지만 .3의 공식 채널이 Stable/Beta로 일치해 정식 채널 포함을 확인. 실제 전체 설치본 활성화는 미검증.
  - P2: 환경 이전 후 수작업으로 재설정하는 비용과 오류의 비교 가능성이 있음.
  - 비교 질문: 같은 작업 환경을 옮길 때 설정·단축키 복원률과 수작업 보정 횟수가 어떻게 다른가?
  - 검증: 테스트 프로필에 사용자 단축키와 비민감 설정을 만들고 다른 프로필로 가져온다.
  - 지표: 이전 값 보존·충돌 처리·누락 설정·수동 재설정 횟수
  - 준비도: conditional. 5.41.429.3 Stable 설치본의 기능 노출·동작 및 OS·계정·한국 제공 조건 확인

[공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)
