# 브라우저별 출처와 점검 주기

2026-10-30부터 적용할 운영 명세. 문서 저장은 자동화 활성화나 수집 완료를 의미하지 않는다. Safari는 추후 별도 검토하며 이번 대상에서 제외한다.

| browser ID | 주기 | 범위 및 공식 출처 |
| --- | --- | --- |
| chrome | 기존 매 실행 | 기존 collection-policy의 Chrome 출처 및 flags |
| edge | 기존 매 실행 | 기존 Stable/Mobile Stable·개발자 블로그 |
| firefox | 기존 매 실행 | 기존 Desktop/Android 릴리스·MDN |
| brave | 기존 매 실행 | https://brave.com/latest/ · https://github.com/brave/brave-browser/releases · https://github.com/brave/brave-browser/blob/master/CHANGELOG_ANDROID.md · https://brave.com/blog/ |
| whale | 기존 매 실행 | https://forum.whale.naver.com/ 의 공지 및 업데이트에서 공식 운영팀 원문, https://whale.naver.com/ 에 연결된 공식 안내 |
| opera | 주 1회 보조 관찰 | https://blogs.opera.com/desktop/ · https://blogs.opera.com/mobile/ · https://blogs.opera.com/news/ 의 주요 제품 발표와 연결된 changelog |
| vivaldi | 주 1회 보조 관찰 | https://vivaldi.com/blog/desktop/ · https://vivaldi.com/blog/android/releases/ 및 연결된 공식 변경 기록 |

## 주기와 완료 판정

기존 실행 일정은 유지한다. Opera·Vivaldi는 첫 실행에서 최근 7일을 점검하고 이후 출처별 마지막 성공 확인으로부터 7일 이상 지난 첫 기존 실행에서 확인한다. 실패한 출처는 다음 기존 실행에서 재시도하며 성공 전 checkpoint를 전진시키지 않는다. 새 주간 자동화는 생성하지 않는다. 점검 예정 전 건너뜀은 성공·변화 없음이 아니다.

모든 출처는 마지막 성공 checkpoint 이후 전체 구간과 직전 7일을 겹쳐 확인한다. 기존 이력이 있으면 이어받는다. 주간 보조 관찰은 주요 공식 발표와 연결된 기록만 대상으로 하며 브라우저 전체 변경 수집 완료로 표시하지 않는다. 선택한 공식 자료에서는 PM 선별 전 항목·유형·수집 범위를 보관한다.

브라우저·플랫폼·출처별 checkpoint와 다음 확인 시점을 비공개 상태로 유지한다. 수집 결과를 영속 저장한 후에만 checkpoint를 전진시킨다. 공개 문서에는 확인 범위·한계만 남긴다.

## 제품별 오판 방지

- Windows·Android 우선. Desktop 발표를 Android에 자동 적용하지 않는다.
- Brave는 일반 Brave와 별도 제품/에디션, Stable/Beta/Nightly를 구분한다. Wallet·광고·검색 변경은 수집 범위에 기록하되 브라우징 영향으로 PM 선별한다.
- Whale은 운영팀의 발표 본문과 사용자 댓글·제보를 구분한다. 댓글 작성일을 출시일로 사용하지 않는다. Desktop/Android와 Stable/Beta를 구분한다.
- Opera는 일반 Desktop/Android를 기본 범위로 삼는다. GX·Mini·Neon 등 다른 제품은 일반 Opera와 혼합하지 않고 관련 발표의 제품명을 명시한다.
- Vivaldi는 Stable과 Snapshot을 구분한다. UI 사용자 설정·탭 관리 등은 검토 관점이며 수집 원문을 제한하는 필터가 아니다.
- Chromium 기반이라는 이유로 Chrome 기능·flags가 다른 브라우저에 제공된다고 판단하지 않는다. 각 제품의 실제 도입 근거·버전을 확인한다.
- 동일 엔진 변경은 브라우저별 도입 사건을 연결하되 동일 브라우저·범위의 반복 발표는 중복 제거한다. 공통 엔진 설명은 보고서에서 묶어 중복 설명을 줄인다.
- 기존 releases/<browser>/<version>, features/<browser>, data/events와 reports/pc·mobile·ai 구조를 재사용한다. 새 browser ID는 brave/whale/opera/vivaldi이며 실제 수집 전 빈 결과를 만들지 않는다.

## 한국 시장 확인

Google 한국 블로그 https://blog.google/intl/ko-kr/ 와 Microsoft 한국 뉴스룸 https://news.microsoft.com/source/asia/region/korea/?lang=ko 를 확인한다. 모든 대상 브라우저의 기능별 공식 도움말에서 국가·언어·계정·구독 조건을 확인한다. 한국 뉴스 채널이 없는 제품은 글로벌 공식 문서의 한국 제공 조건을 확인하며 한국어 문서가 없다는 이유로 미지원으로 판단하지 않는다.

한국 발표는 해당 브라우저의 주기(매 실행 또는 주간)에 맞춰 확인한다. selected/watch와 한국 지원 확인이 필요한 pending_verification의 지원 조건 문서는 주 1회 확인하고 관련 새 근거 발견 시 앞당긴다. 지원 국가·언어·계정 조건 본문을 이전 기록과 비교한다. 최초 확인은 baseline이며 문서 수정일·최초 발견일을 출시일로 사용하지 않는다.

기존 schema를 깨지 않도록 scope 또는 연결된 기능 문서에 다음을 기록한다.
- 한국 제공: 지원 명시 / 단계적 배포 / 예정 / 미지원 명시 / 미확인
- 한국어 지원: 지원 / 부분 지원 / 미지원 / 미확인
- 플랫폼·계정·구독·기기·연령 조건, 공식 근거·확인일·한국 적용일
- 실기 검증: 미실행 / 노출 확인 / 동작 확인 / 테스트 환경에서 미노출

문서가 상충하면 근거를 보존하고 해당 사항은 미확인으로 둔다. 한국어 문서 존재나 서비스 전체 지원을 개별 브라우저 기능의 한국 출시 근거로 삼지 않는다. 한국 확대·한국어 지원 추가·제공 중단은 기존 feature에 연결한 새 사건 후보로 선별한다. 한국 미지원만으로 글로벌 후보를 제외하지 않는다. 번역·baseline·backfill은 재알림하지 않는다.

실기 환경이 없으면 미실행으로 기록하고 공식 수집·게시를 계속한다. 직접 시험 시 OS·브라우저 버전·언어·지역·계정 유형·VPN·flags 조건을 기록하되 계정 주소·IP는 공개하지 않는다. 한 기기의 미노출이나 우회 활성화를 한국 전체 제공 상태로 일반화하지 않는다.
