# 웹툰 제작 후 대시보드 동기화

이 절차는 기존 ‘브라우저 웹툰 제작’ 예약 작업의 마지막 단계에 추가합니다.
기존 제작 일정, 제작 수, 검수와 전달 절차는 유지합니다. 별도 예약 작업을 만들지 않습니다.
이 파일을 저장하는 것만으로 예약 작업 설정이 변경되지는 않습니다.

## 예약 작업 지침에 추가할 문장

> 기존 웹툰 제작과 Notion 기록을 마친 뒤, sangria-kim/browser-benchmark 저장소의 work/browser-benchmark 브랜치에서 dashboard/SCHEDULE_COMPLETION.md를 읽고 공개 대시보드 상태 동기화 절차를 수행한다. Notion ‘브라우저 업데이트 웹툰 제작실’의 후보 상태와 ‘04 최종 결과 · 시안 보관’의 검증된 완성본을 사건별로 대조하여 dashboard/webtoons.json에 반영하고, 저장소 규칙에 따라 work 브랜치에 게시한 commit SHA와 재조회 결과를 확인한다. 동기화가 실패하면 제작 결과를 보존하고 실패 사실을 보고하며, 동기화 성공으로 표시하지 않는다.

## 상태 확인

1. Notion 제작실의 후보 목록과 최종 결과 보관 페이지를 읽습니다.
2. `data/events/*.json`과 브라우저, 기능, 플랫폼, 버전, 채널을 대조합니다. Safari도 같은 규칙을 적용합니다. 제목 유사성만으로 연결하지 않습니다.
3. 후보 통과는 `todo`, 현재 후보 제외는 `excluded`로 기록합니다. 최종 PNG/PDF 첨부와 해당 기능을 확인했을 때만 `done`으로 기록합니다. 초안이나 제작 예정 기록은 완료가 아닙니다. 발송 여부는 제작 완료와 구분합니다.
4. Beta 등 채널 차이는 `scope`와 `note`에 명시합니다. 다른 플랫폼을 같은 완료로 연결하지 않습니다. 대응 사건이 없으면 상태를 추측하지 않고 기존 항목을 보존합니다.

## 공개 파일 갱신

- `dashboard/webtoons.json`을 읽고 확인한 사건 항목만 갱신합니다. 기존 나머지 항목을 보존합니다.
- 최상위 필드는 `schema_version: 1`, ISO 날짜/시간 `checked_at`, `events`입니다. `checked_at`은 실제 Notion 대조 시각입니다. 확인하지 못했다면 갱신하지 않습니다.
- `events`의 키는 정확한 `event_id`입니다. 값은 `status`, 선택적 `url`, `scope`, `note`만 허용합니다.
- `done`에는 최종 결과 Notion 페이지의 안정적인 HTTPS URL이 필수입니다. 만료 첨부 URL이나 검색/추적 매개변수가 붙은 URL은 쓰지 않습니다.
- `scope`와 `note`는 공개 브라우저 기능과 제작 범위만 설명합니다. 계정, 연락처, 이메일, 로그, 내부 분석, 비밀값은 넣지 않습니다. Notion 접근 권한은 변경하지 않습니다.
- 기존 `catalog.json`의 공식 이미지·영상은 이 절차에서 수정하지 않습니다.

구조 예시입니다. `example-event-id`는 실제 사건 ID로 바꿉니다.

```json
{
  "schema_version": 1,
  "checked_at": "2026-11-16T08:45:00+09:00",
  "events": {
    "example-event-id": {
      "status": "todo",
      "scope": "Safari · macOS",
      "note": "후보 통과, 최종 결과 미완성"
    }
  }
}
```

## 검증과 게시

1. 저장소 `AGENTS.md`를 따릅니다. 최신 work/main을 확인하고 동시 변경을 보존합니다.
2. JSON 구문과 공개 필드를 확인합니다. 로컬 실행이 가능하면 `node --test tests/webtoon-feed.test.cjs`와 `python3 -m unittest discover -s tests -v`를 실행합니다. 클라우드 연결 도구만 있으면 같은 검증 기준을 적용하고, push 후 GitHub Actions 결과를 확인합니다.
3. GitHub 연결 도구 또는 인증된 Git으로 `work/browser-benchmark`에 게시합니다. 연결 도구에서는 읽어 둔 최신 head SHA를 부모와 expected_sha로 사용하고 force는 false로 설정합니다. 충돌이면 최신 파일을 다시 읽고 항목별로 합칩니다. main에 직접 쓰거나 PR을 merge하지 않습니다.
4. work → main PR을 생성하거나 기존 열린 PR을 갱신합니다. 소유자가 검토하도록 열어 둡니다.
5. 게시한 commit SHA의 raw 파일을 다시 읽어 이번 상태와 링크를 확인합니다. 실패나 미검증 CI를 성공으로 보고하지 않습니다.

## 화면 반영

대시보드 코드가 main에 배포되면, 열린 화면은 공개 work 브랜치의 이 파일을 5분마다 조회합니다. 새로고침 버튼으로 즉시 확인할 수도 있습니다. GitHub API로 파일의 최신 commit SHA를 얻고 그 SHA에 고정된 내용을 읽습니다. 화면은 가져온 SHA와 ‘소유자 검토 전 자료’를 표시합니다. 이 상태 피드는 PR merge 전에도 화면에 반영됩니다. 코드와 조사 자료는 기존 main 배포 절차를 유지합니다.

조회 제한·네트워크 장애·잘못된 데이터·이전 시점의 스냅샷은 기존 표시를 유지하고 지연으로 표시합니다. 화면을 닫았다가 열면 배포본 카탈로그를 먼저 표시한 뒤 다시 조회합니다. 대시보드는 Notion 인증 토큰을 보관하거나 Notion을 직접 호출하지 않습니다.
