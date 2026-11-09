# 멀티플레이 팔로우의 자동 종료 규칙

- browser: whale
- canonical feature key: `multiplay`
- feature_id: `whale-multiplay`

## 기존 기능과의 관계

기존 도움말은 수동 스크롤·탭 이동 시 팔로우 중지와 알림을 설명한다. 이번은 두 차례 다른 탭 이동 후 자동 종료 규칙이다. 중지와 종료를 동일하게 취급하지 않으며 실제 상태 전이는 별도 검증한다.

## 이력

- 2026-11-03: 공식 Desktop 공지 등록. 본문 Beta 날짜는 2026-11-02.
- 2026-11-04 KST: 공식 본문·기존 기록·도움말 대조 후 아래 동작 변화 선정. 실제 기기 시험은 미실행.
- 두 번 탭 이탈 시 팔로우 종료; 분할 새 탭·마이크 단축키·프로필 툴팁 보완 · P2 · [사건](../../data/events/whale-desktop-multiplay-follow-exit-5-41-429-2-20261102.json).

[19개 전체 항목](../../releases/whale/5.41.429.2/items-desktop-assessment-2026-11-04.json) · [상세 분석·시험 후보](../../reports/2026-11-04.md).

## 범위와 불확실성

홈페이지 한국어·영문 공지와 연구소 제목·한국어 본문은 Beta. 연구소 영문 본문의 Stable, Beta 표기는 상충하며 Stable 제공은 미확인.

Desktop Beta 5.41.429.2. 항목별 OS·국가·언어·구독·연령·단계 배포 조건은 미공개. 한국어 공지 존재만으로 한국 제공·한국어 기능 지원을 확정하지 않음. 실제 지원 OS는 미확인이며 Desktop을 Windows·macOS·Linux 전체 지원으로 확장하지 않습니다.

## 2026-11-07 관찰: Desktop 5.41.429.3

공식 본문의 배포 표기는 2026-11-06 Stable/Beta다. 동일 URL의 최초 등록일 11/3과 구분하며, .2 Beta의 기존 기록을 변경하지 않는다. 한국 제공·한국어 지원은 각각 미확인, 실기 미실행이다.

- [whale-desktop-multiplay-follow-exit-5-41-429-3-stable-20261106](../../data/events/whale-desktop-multiplay-follow-exit-5-41-429-3-stable-20261106.json): 기존 .2 Beta 기능의 소개는 반복이지만 .3의 공식 채널이 Stable/Beta로 일치해 정식 채널 포함을 확인. 실제 전체 설치본 활성화는 미검증.
  - P2: 협업 화면 따라가기에서 개인 탐색으로 전환하는 제한된 동작 규칙 개선.
  - 비교 질문: 공동 탐색 중 스스로 다른 탭을 볼 때 팔로우 상태를 이해하고 통제하기 쉬운가?
  - 검증: 테스트 참여자 환경에서 팔로우 중 한 번 및 두 번 탭을 이탈하고 듀얼 탭을 연다.
  - 지표: 두 번째 이탈의 해제 타이밍, 공유 상태 인지, 예상치 못한 팔로우 지속 여부
  - 준비도: conditional. 5.41.429.3 Stable 설치본의 기능 노출·동작 및 OS·계정·한국 제공 조건 확인

[공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)

## 화면 공유 대상 선택과 공유 탭 이동 설명

Desktop 5.41.429.3 Stable/Beta의 공식 한국어·영어 공지와 운영팀 본문은 다음 두 동작을 설명합니다.

- 화면 공유 버튼에서 현재 창이나 다른 창·화면을 선택합니다.
- 다른 사람이 공유 중인 탭으로 바로 이동합니다.

[공식 도움말](https://help.whale.naver.com/ko/desktop/multiplay/)은 이미 화면 공유 버튼에서 화면·창을 고르는 절차와, 공유 화면을 맨 앞 탭에 표시하는 동작을 설명합니다. 따라서 화면 공유 자체의 신규 도입으로 해석하지 않습니다. 현재 창 선택·공유 탭 이동의 정확한 UI 차이와 최초 제공 시점은 미확인입니다.

공지 본문의 2026-11-06은 버전 배포 표기입니다. 공지 수정일이나 2026-11-10 근거 확인일을 기능 출시일로 사용하지 않습니다. 개별 기능의 적용일, OS·국가·언어·계정·구독·단계 배포 범위는 미확인입니다. 한국어 문서가 있다는 사실만으로 한국 제공·한국어 지원을 확정하지 않습니다. 직접 동작 검증은 미실행입니다.

- 판정: pending_verification. 기능 설명은 공식 확인됐지만 기존 기능과의 차이·최초 제공 시점은 미확인입니다.
- 비교 질문: 공동 탐색 중 공유할 대상을 잘못 고르거나 상대의 공유 탭을 찾는 부담을 줄이는가?
- 재검토: 같은 OS의 이전·현재 빌드에서 메뉴 위치·선택 단계·공유 탭 이동을 비교하거나 공식 최초 도입 설명을 확인합니다. 실제 공유에는 별도 허용된 시험 참가자와 공개 시험 페이지만 사용합니다.

[기능 근거](../../releases/whale/5.41.429.3/items-multiplay-evidence-2026-11-10.json) · [공식 한국어](https://notice.naver.com/notices/whalehomepage/35247) · [공식 영어](https://notice.naver.com/notices/whalehomepage/35248) · [운영팀](https://forum.whale.naver.com/topic/63213/)
