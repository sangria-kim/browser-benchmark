# Whale 수집 및 색인 검증

2026-11-03 보완 기준: `5c956bc38d99fcc42da022924320029e800bb6d2`, `pm-selection-v2`.

저장소 조사 결과 기존 코드는 Chrome 캐시 이력 생성용 `scripts/build_flag_archive.py`뿐이다. Whale 네트워크 수집기·스케줄러·CI workflow·기계 판독 JSON Schema는 없었다. 기존 문서와 릴리스 JSON 구조를 유지한다. 이번에 추가한 도구는 **수동/에이전트 수집 후 검증기**이며 네트워크 수집, 게시, 메일, checkpoint 갱신을 하지 않는다. 자동화 실행 설정 자체를 수정한 것으로 주장하지 않는다.

1. [공식 출처 규칙](browser-sources-and-cadence.md)에 따라 목록 기간과 제품별 본문을 읽는다. HTTP 200의 빈 JS shell은 본문 성공이 아니다. 렌더링된 공식 본문을 사용했다면 그 방법을 기록한다.
2. 본문의 한국어 최상위 개선·수정 항목을 각각 한 item으로 기록하고 하위 설명을 해당 요약에 포함한다. 원문 전체를 복제하지 않는다. 번역 공지는 같은 제품·버전·변경으로 대조해 중복 제거한다.
3. 기존 릴리스 구조 안에 제품별 파일을 둔다. 이번 Android 4.0은 `4.0/items-android-backfill-2026-11-03.json`이며 기존 iOS 예고 파일은 그대로 둔다. Desktop 기존 reference도 그대로 보존한다. 제품·버전·기능 키를 item_id에 포함한다.
4. `expected_counts`는 원문을 읽어 독립적으로 센 값이다. 추출 결과 길이에서 자동 생성해 완료를 추정하지 않는다. `collection_status=success`는 명시된 단일 본문의 전체 항목만 뜻한다. 게시판 전체 성공과 구분한다.
5. 모든 항목 저장 후 PM 기준을 적용한다. 과거 보완은 excluded, 새 출처의 신규성/전달 이력 미확인은 pending_verification으로 이유·재검토 조건을 보존한다. 단순 관찰만으로 selected나 P1/P2를 부여하지 않는다.
6. 아래 검증, JSON 파싱, 기존 event_id 중복과 변경 파일 상대 링크·공개 범위 검사를 통과한 뒤 함께 게시한다. 원격 최신 head를 확인하고 게시 후 파일을 재조회한다. 그 후에만 실제 완료한 출처 범위의 비공개 checkpoint를 갱신한다.

```sh
python3 scripts/validate_whale_index.py
python3 -m unittest discover -s tests -v
# 특정 신규 색인 검사
python3 scripts/validate_whale_index.py releases/whale/4.1/items-android-backfill-2026-11-03.json
```

검증기는 표준 라이브러리만 사용하며 schema_version=1, 제품/버전 일관성, 필수 선별 필드, 항목·순번 중복, 전체 수량 및 과거 항목의 신규 보고 방지를 검사한다. 과거 모든 JSON에 새 계약을 강제하지 않는다. 본문 진위·누락·PM 판단을 자동 입증하지 않으므로 원문 대조가 필요하다. 테스트는 누락·중복·플랫폼 혼합·과거 재보고·빈 성공·잘못된 순번 및 partial을 포함한다.

## 이번 확인 범위와 한계

공식 iframe 연결은 홈페이지 HTML에서, Android 본문은 렌더링된 공식 페이지에서, Desktop 본문은 운영팀 첫 게시글에서 확인했다. 게시판 전체 목록 첫 페이지에서 11/2 Android 4.1과 그 이전 10/8 공지를 확인했다. 전체 과거 페이지와 모든 제품별 필터의 전체 본문은 미수집이다.

- Desktop 5.39.412.57: 개선 20 + 수정 7. 본문 10/1 Stable/Beta, 목록 등록 9/17과 구분. 기존 요약을 대체 삭제하지 않고 27항목 backfill 추가.
- Android 4.0: 개선 11 + 수정 2. 등록 10/8, 배포 10/7. 과거 baseline 보완.
- Android 4.1: 개선 2 + 수정 2. 등록 11/2, 배포 10/29. 기존 전달 이력과 기능별 신규성·조건 대조 전 pending_verification. 아침 수집 당시 누락이라고 단정하지 않는다.
- iOS 4.0: 기존 최소 OS 예고만 보존. 이번 수집 성공 주장 없음.
- 제품 소개 15문구의 partial 상태는 해소되지 않았다. 설치본·실기·한국 제공 조건은 검증하지 않았다.

상세 신규 보고·메일은 만들지 않으며 일정을 변경하지 않는다. 44개는 항목 수이지 신규 기능·알림 수가 아니다.
