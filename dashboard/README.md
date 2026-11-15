# 브라우저 관측소

의존성 설치 없이 실행하는 정적 대시보드입니다. 화면은 한국어이며 다크 테마를 사용합니다.

```sh
python3 scripts/build_dashboard.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

http://127.0.0.1:8765 에서 확인합니다. 저장소의 하위 URL에서도 작동하도록 상대 경로를 씁니다.

## 화면과 집계

- 브라우저 카드: 고유 `feature_id` 수와 최신 근거 확인일(KST).
- 기능 테이블: `data/events/*.json`의 변경 사건별 행. 같은 기능의 여러 사건을 보존합니다.
- 검색, 플랫폼, 웹툰 상태, AI 필터, 정렬, 20행 단위 페이지 이동. 필터는 URL에 보존됩니다.
- 펼친 행: 변경 전후, 제품 조건, 공식 근거, 실제 예시, 웹툰, 같은 기능의 다른 사건.
- Chrome flags: `experiments/chrome/*.md`의 flag별 문서 전체. 검색, 소스 플랫폼, 변경 유형, 타임라인과 원문 링크.
- 과거 reports 중 구조화 사건으로 변환되지 않은 내용은 기능 테이블에 포함되지 않습니다. 기존 reports와 releases는 삭제하지 않습니다.
- flag 등록·삭제, 만료 milestone, 소스 기본값은 제품 출시·철회·최소 버전이 아닙니다.

## 웹툰과 예시

`catalog.json`은 사건 ID에 연결하는 최소 공개 카탈로그입니다. Notion 원문이나 운영 로그를 복제하지 않습니다. 완성본 링크는 사용자가 요청한 웹툰 바로가기이며 Notion 공유 권한은 바꾸지 않습니다. 원래 접근 권한이 없는 방문자는 링크 내용을 읽을 수 없습니다.

상태 값은 다음 세 가지입니다.

| 값 | 화면 | 원본 의미 |
| --- | --- | --- |
| `todo` | 작업 전 | 만들 예정(후보 통과) |
| `done` | 작업 완료 | 최종 완성 PNG/PDF와 기능·플랫폼 대응 확인 |
| `excluded` | 작업 대상 아님 | 현재 후보 아님. 영구 제외와 일시 장애는 note로 구분 |

미연결은 제작 상태가 아닙니다. 대응 기록이 없을 때 `webtoon`을 생략합니다. 조사 `selection_status`에서 웹툰 상태를 추정하지 않습니다. 완성 웹툰이 Beta 등 다른 채널의 화면을 사용하면 `scope`와 `note`에 명시합니다. 다른 플랫폼의 웹툰을 해당 사건의 완료로 연결하지 않습니다.

`media`에는 검증된 공식 이미지·영상의 안정 URL만 넣습니다. `type`은 image/video/link, `url`은 HTTPS, `label`과 `note`에는 화면과 촬영 조건을 적습니다. 만료되는 Notion 첨부 URL은 쓰지 않습니다. 직접 시험과 공식 시연은 구분합니다.

현재 카탈로그는 `checked_at`에 대조한 스냅샷입니다. Notion을 실시간 조회하는 연동은 아닙니다. 기존 웹툰 제작 작업은 완료 시 해당 사건의 catalog 항목과 checked_at을 갱신하는 방식으로 연결할 수 있습니다. 먼저 브라우저·기능·버전·플랫폼·최종 첨부를 대조하고, event_id 단위로 갱신한 뒤 아래 검증과 저장소 PR 절차를 따릅니다. 스케줄 설정과 Notion 데이터는 이 대시보드가 수정하지 않습니다.

## GitHub Pages

1. 저장소 Settings → Pages → Source를 **GitHub Actions**로 설정합니다.
2. 작업 PR을 소유자가 검토하여 main으로 merge합니다. agent는 merge하지 않습니다.
3. Browser dashboard workflow가 빌드한 `dist`를 Pages에 배포합니다.

기대 경로는 `https://sangria-kim.github.io/browser-benchmark/`입니다. 실제 배포 성공은 Actions 결과를 확인하세요. work 브랜치와 PR은 빌드만 합니다. main 변경마다 자료와 카탈로그를 다시 빌드합니다. 소스 브랜치와 commit SHA는 화면 하단에 기록됩니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
node --check dashboard/app.js
```

빌드는 사건 ID 중복, 알 수 없는 카탈로그 ID, 잘못된 상태, 완료 링크 누락을 거부합니다. 브라우저에서는 카드 선택, 복합 필터, 빈 결과, 상세 펼침, 미디어, flags, 작은 화면을 확인합니다.
