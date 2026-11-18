# 브라우저 벤치마크 대시보드

공개 대시보드는 **브라우저 보드**로 열립니다. 상단에서 **관측소**를 선택하면 같은 날짜와 카드를 어두운 집계·검색 화면에서 볼 수 있습니다. 보드는 제품별 열을 사용합니다. 관측소는 브라우저별 수를 눌러 카드를 좁힙니다. 화면 선택은 같은 브라우저에 저장합니다.

- 수집일은 한국시간입니다. 기능 사건을 모두 표시하고 일일 선정 리포트에 처음 기록된 원천 전용 기능도 포함합니다. 같은 날 같은 기능에 연결된 동일 문서 내용은 한 카드에 모읍니다. 소스 실험, 계획, 베타와 과거 보강의 단계를 카드에 표시합니다.
- 날짜를 고른 후 한글 제목, 브라우저 별칭, 버전이나 플랫폼을 검색할 수 있습니다. 카드 상세에는 적용 조건, 변경 내용, 공식 화면과 근거 링크가 있습니다. **자료 탐색**에서 기존 선정 이력과 Chrome 실험, 원천 자료, 리포트 revision을 확인하세요.
- **뉴스레터**에는 그날 수집 카드 중 최대 세 가지 변화와 삼성 브라우저 검토 질문 두 개를 싣습니다. 호 날짜와 실제 생성일을 각각 표시합니다. 원하는 생성일과 호를 선택해 A4 한 장으로 인쇄하거나 PDF로 저장하세요. 수집이 일부만 끝난 호에는 그 상태를 표시합니다.
- 초기 18개 호는 2026년 11월 19일에 과거 수집 자료로 생성했습니다. 이후 일일 리포트가 생성되면 같은 트랜잭션에서 뉴스레터 사본도 저장합니다. 이전 revision은 보관함에서 열 수 있습니다. 발행 전인 수집일은 뉴스레터 탭에서 미리 볼 수 있습니다. 생성일 보관함에는 저장된 호만 표시합니다. 다음 리포트를 생성할 때 이전 수집일의 미발행 호도 함께 저장합니다.
- PR의 Actions 실행에서 **daily-dashboard**를 내려받고 압축을 풀어 `index.html`을 여세요. 카드와 뉴스레터는 오프라인에서도 열립니다. 외부 화면·영상과 원본 자료 링크는 인터넷 연결이 필요합니다.

새 영문 자료는 [한글 제목](daily/titles.json), [원천별 문구](daily/source-copy.json)와 확인된 동작 표현을 적용합니다. 한글 제목을 만들 근거가 부족하면 **한글 기능 제목 편집 대기**를 표시하고 원문은 상세에 둡니다. 이 항목은 뉴스레터의 편집 대기 수에 포함합니다. 카드 ID로 제목을 등록하면 다음 빌드부터 카드에 적용됩니다.

## 화면 자료 보강

1. **화면 미확보만**을 선택하고 해당 카드를 여세요. **화면 자료 추가**에서 해당 버전·플랫폼의 이미지 또는 영상 HTTPS 주소를 입력하세요.
2. 미리보기에서 내용을 확인하고 저장하세요. 이 브라우저에 저장한 주소는 두 디자인에서 함께 사용합니다. 등록 해제도 가능합니다.
3. 팀에 공유할 때는 [미디어 카탈로그](catalog.json)에 카드 ID로 `media`를 등록하세요. 기능 사건은 `events`, 원천 문서 카드는 `sources` 아래에 둡니다. 자료 형식(`image` 또는 `video`), 공개 HTTPS 주소, 한글 설명과 확인한 범위를 기록하세요. 다음 빌드에서 모든 사용자에게 표시됩니다.

## 대시보드 디자인 시안

[시안 갤러리](concepts/gallery.webp)에서 우선 후보 01 모닝 에디션·03 브라우저 보드와 추가 시안 세 개를 비교하세요. 이전 02·04·05도 접힌 목록에서 열 수 있습니다.

- **06 관측소 대시보드**는 [운영 GitHub Pages](https://sangria-kim.github.io/browser-benchmark/)의 스타일시트를 사용합니다. 날짜를 고른 뒤 브라우저별 집계와 검색으로 발췌 카드를 좁히세요.
- **07 업데이트 달력**은 자료가 있는 날을 월간 달력에 표시합니다. 카드에서 뉴스레터로 전환하면 같은 호의 발행일이 선택됩니다.
- **08 사용 장면 상영관**은 사용자 과제를 장면으로 제시합니다. 장면을 선택해 바뀐 동작과 실제 화면을 보고, 상영 프로그램 형태의 뉴스레터를 인쇄할 수 있습니다.

[추가 시안 세 화면 비교](concepts/round-two.webp)

PR의 Actions 실행 결과에서 `dashboard-design-preview`를 내려받아 압축을 풀고 `index.html`을 여세요.
로컬에서는 `python3 scripts/build_design_concepts.py`로 같은 HTML을 생성합니다.
출력 경로는 `dist/concepts/index.html`입니다. 공식 이미지와 영상은 온라인에서 불러옵니다.

각 시안은 11월 6일·10일·11일(KST) 수집 자료에서 발췌한 카드 9건을 사용합니다.
수집일은 사건의 `observed_at`을 기준으로 합니다. 예시 뉴스레터는 다음 날 발행을 가정합니다.
날짜별 첫 카드를 주요 기사로 싣고, 다른 카드의 제목과 최대 두 가지 삼성 브라우저 비교 질문을 한 장에 담습니다.
뉴스레터에서 발행일을 선택하거나 인쇄할 수 있습니다. 시안별 디자인 참고 사이트는 갤러리 아래에 있습니다.

카드 상세는 같은 사건 ID에 연결된 공식 화면을 보여 줍니다.
화면 미확보 필터에서 자료가 필요한 카드를 다시 찾을 수 있습니다.
상세에서 이미지·영상 주소를 미리 보고 저장하면 같은 브라우저의 다른 시안에서도 열립니다. 로컬 등록을 해제하면 미확보 목록에 다시 나타납니다.
공유 자료에 반영하려면 확인한 자료를 [미디어 카탈로그](catalog.json)의 해당 사건에 추가하고 시안을 다시 생성하세요.

```sh
python3 -m pip install -r schemas/requirements.txt
python3 scripts/build_dashboard.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

`http://127.0.0.1:8765`에서 확인합니다. 빌드는 기존 T5 선택 모듈을 사용합니다.
수집, 평가, 예약 작업 또는 외부 요청을 실행하지 않습니다. 프런트엔드에는 새 패키지가 없습니다.
배포 자산은 상대 경로를 사용하므로 GitHub Pages의 저장소 하위 URL에서도 작동합니다.

## 자료 탐색 화면과 집계

- 자료 탐색 화면은 `data/selected/features/current.json`의 현재 선정으로 열립니다. Chrome 실험 탭은 `flags/current.json`을 사용합니다.
- 상단 브라우저 박스의 수는 **현재 선정 기능 항목** 수입니다. 원천만 있는 선정 대상도 포함합니다. 날짜는 그 대상의 근거 확인일(KST)입니다.
- Safari도 항상 표시합니다. 현재 선정이 없다는 표시는 수집 자료가 없다는 뜻이 아닙니다. 빈 선정 결과에서 전체 자료로 이동하면 브라우저 조건을 유지합니다.
- 카드의 큰 제목은 기능과 변화를 짧게 요약한 한글 문구입니다. 원래 제목은 제목에 마우스를 올리거나 상세를 열어 확인합니다. 작은 화면에서는 요약을 자르지 않고 줄바꿈합니다.
- [card-summaries.json](card-summaries.json)은 현재·과거 선정 및 일일 리포트의 표시용 요약입니다. 원문 제목이 일치할 때만 적용합니다. 같은 제목으로 서로 다른 변화가 있는 경우 사건 ID도 확인합니다. 새 항목이나 전체 자료 중 요약이 등록되지 않은 항목은 원문 제목을 유지합니다. 원본 사실과 보존된 리포트는 변경하지 않습니다.
- 카드에는 브라우저, 플랫폼, 관찰 버전, 확인일과 웹툰 상태 또는 실험 종류를 표시합니다. 채널, 지원 여부, 소스 근거 수준과 판단 사유는 상세에 둡니다.
- 검색은 한글 요약과 원문 제목을 모두 찾습니다. 이름순 정렬은 표시된 요약을 기준으로 합니다. 플랫폼, 확인일 범위, 웹툰 상태, AI, 정렬과 18개 단위 페이지 이동을 제공합니다. 실험에는 종류, 변경 유형과 빌드 조건 필터가 있습니다.
- 실험 종류 `flag_entry`, `base_feature`, `command_switch`는 별도 필터와 개수를 갖습니다. source OS mask는 설치본 지원 범위가 아닙니다.
- 과거 선정 포함은 현재 투영의 고유한 선정 변화 대상입니다. 과거 스냅샷을 합쳐 변경을 중복 집계하지 않습니다. 대표 사건이 교체된 이전 선정 대상도 남습니다.
- 판단 기준일은 그 날 KST 종료 시점의 T5 판단 투영입니다. 판단이 생긴 날짜를 제공합니다. 날짜 사이에 새 판단이 없으면 앞선 날짜와 같은 상태입니다. 당시 저장된 원천 사실 전체를 재현한다는 뜻이 아닙니다.
- 상세는 선택일 판단, 현재 판단, 현재 대표 대상을 구분합니다. 다른 사건으로 대표가 바뀌어도 이전 사건에 PM 선정 해제 판정을 만들지 않습니다.
- 전체 자료 탐색은 원천, 기능 카탈로그, 실험 카탈로그를 구분합니다. 기본값은 모든 원천 항목이며 선정 자료로 제한하지 않습니다. 연결된 원천의 PM 필터는 대표 평가 대상의 판단을 사용합니다. 상세에서 대표 대상을 확인할 수 있습니다.

## 상세와 리포트

상세 파일은 고유 대상 ID에 연결합니다. 사건 상세는 해당 사건의 사실을 사용합니다.
현재 카탈로그의 기본값이나 만료 값을 과거 사건에 덮어쓰지 않습니다.
원본·정정 아카이브, 사실 전후, 현재 보존 근거, 판단 이력, 선정 변화, 관계, 문서와 관련 리포트를 확인할 수 있습니다.
원천에만 존재하는 항목은 기능 사건으로 표시하지 않습니다.

일일 리포트는 날짜와 revision으로 이동합니다. 브라우저와 기능/실험으로 좁힐 수 있습니다.
항목을 열면 리포트에 동결된 사실 요약, 판단, 날짜, 출처 revision/hash를 먼저 표시합니다.
그 아래 같은 ID의 현재 사실·판단을 명시적으로 구분합니다. 초기 기준선과 과거 보강은 신규 출시가 아닙니다.
수집·평가가 미완료인 리포트를 변화 없음으로 표시하지 않습니다.
기존 수동 리포트와 flag Markdown 문서도 삭제하지 않습니다. 기존 flag 전문과 타임라인은 상세에서 열 수 있습니다.

## 정적 데이터 분할

`build()`의 기존 반환값 `events`, `flags`, `catalog`, `source`는 유지합니다. `research`가 새 화면의 진입 자료입니다.
기존 원본 사건 필드는 그대로 반환합니다. `dist/data.json`은 큰 과거 전문을 포함하지 않습니다.

| 출력 | 내용 |
| --- | --- |
| `data.json` | 현재/과거 선정 요약, 날짜·리포트 목록, 집계와 정확한 사건별 미디어 카탈로그 |
| `indexes/{source_item,feature,experiment}.json` | 전체 탐색에서 필요한 계층의 검색 요약 |
| `details/<SHA256 of kind:id>.json` | 해당 ID의 사실, 판단, 출처, 관계, 과거 문서 |
| `dates/YYYY-MM-DD.json` | T5 API가 계산한 KST 종료 시점 선정 목록 |
| `reports/YYYY-MM-DD-rN.json` | 원본 보고서 revision과 동일한 동결 JSON |

대상 및 리포트 파일은 선택할 때 불러오며 성공 결과를 메모리에 재사용합니다.
원천 텍스트는 명령으로 처리하지 않습니다. HTML을 이스케이프하고 외부 링크와 미디어는 HTTPS만 허용합니다.

## 웹툰과 미디어

`catalog.json`의 사건 ID별 매핑과 검증된 미디어를 그대로 사용합니다.
다른 사건, 플랫폼 또는 채널의 웹툰을 자동 상속하지 않습니다.
완성본이 다른 채널의 화면을 쓴 경우 기존 `scope`와 `note`를 그대로 표시합니다.

| 상태 | 화면 | 의미 |
| --- | --- | --- |
| `todo` | 작업 전 | 후보 통과 |
| `done` | 작업 완료 | 최종 완성본과 대응 범위 확인 |
| `excluded` | 작업 대상 아님 | 현재 후보가 아님 |

대응 기록이 없으면 카드에 상태 배지를 붙이지 않습니다. 상세에서 기록 부재를 설명합니다.
필터에는 세 상태만 제공합니다. PM 판단에서 웹툰 상태를 추정하지 않습니다.
Notion 링크는 기존 공유 권한을 사용합니다. 원래 접근 권한이 없는 방문자는 읽을 수 없습니다.

`webtoon-feed.js`의 상태 피드는 `work/browser-benchmark`를 SHA로 고정해서 읽습니다.
자동 확인은 화면이 열린 동안 **매일 09:00 / 10:00 KST만** 실행합니다.
페이지 진입 시 즉시 조회, 5분 간격 조회, 놓친 시간 재실행은 없습니다.
수동 새로고침과 실패 시 마지막 성공 자료 유지 동작은 보존합니다.
상태 피드는 소유자 검토 전 후보 자료이며 화면에 ref와 SHA를 표시합니다.
기존 예약 작업 연결 절차는 [SCHEDULE_COMPLETION.md](SCHEDULE_COMPLETION.md)를 따릅니다.

## GitHub Pages와 검증

Pages Source는 GitHub Actions입니다. work 브랜치는 검증 후보입니다.
소유자가 main에 merge하면 기존 workflow가 빌드와 Pages 배포를 수행합니다.
에이전트는 main에 push하거나 PR을 merge하지 않습니다.
예상 공개 경로는 <https://sangria-kim.github.io/browser-benchmark/>입니다.

```sh
python3 -m unittest discover -s tests -v
node --check dashboard/app.js
node --test tests/webtoon-feed.test.cjs tests/research-ui.test.cjs
```

데이터 검증은 현재/날짜별 선정 계약, 전체 계층 수, 같은 ID 상세, 동결 리포트,
원본 사건·미디어·flag 전문 보존과 초기 payload 크기를 검사합니다.
브라우저 검증에서는 데스크톱·모바일, 필터 조합, 빈 결과, 페이지 이동,
키보드 탭 이동, 상세 열기·Escape·포커스 복원, 과거 사건과 리포트 이동을 확인해야 합니다.


## Generated JSON resources

The builder keeps `data.json` as plain JSON. It declares `resource_encoding: "gzip"` and points to lazy `details/`, `indexes/`, `dates/` and `reports/` resources with explicit `.json.gz` names. Computed detail links use the same encoding. Gzip headers omit local filenames and use a zero timestamp. A rebuild replaces these generated resource directories, so stale plaintext copies do not inflate the site. Use a dedicated output directory.

The browser loader accepts older plain `.json` resources. For `.json.gz`, it checks the gzip magic bytes and uses the native [DecompressionStream API](https://compression.spec.whatwg.org/#decompression-stream). If Fetch has already decoded HTTP `Content-Encoding: gzip`, it reads the returned JSON without decompressing twice. HTTP, decoding and unsupported-browser errors remain visible; failed loads are removed from the cache so the same action can retry. No runtime dependency is downloaded.

Only generated Pages assets are compressed. Repository evidence, export packages and company import contracts remain unchanged. The complete source index still has its original decoded payload and memory cost. A smaller static build does not establish collection completeness or a successful deployment. Check actual generated content bytes against the [GitHub Pages size limit](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) before publishing.
