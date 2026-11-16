# 사내 자료 반입 지침

공개 브라우저 조사 **자료만** 사내 저장소의 지정 하위 경로로 반입한다.
공개 브랜치와 Git 이력을 사내 원격 저장소에 그대로 push하지 않는다.
사내 대시보드, workflow, 루트 지침은 사내 저장소가 관리한다.

## 반입할 자료

정확한 허용 목록은 `config/export-allowlist.json`이다. 디렉터리 전체를
임의로 복사하지 않는다. exporter가 선택하고 verifier가 확인한 파일만 사용한다.

| 자료 | 용도 |
| --- | --- |
| 전체 원천 목록과 출처 근거 | PM 제외 항목과 미해석 항목까지 확인 |
| 전체 기능·Chrome 실험 카탈로그 | flag, base feature, switch를 구별 |
| 기능·실험 사건 및 revision 이력 | 변경 전후와 공개 근거 확인 |
| 전체 PM 판정 이력 | 선정·관찰·검증 대기·제외와 판정 변경 확인 |
| 현재·날짜별 선정 기능과 flag | 현재 화면과 과거 판단 조회 |
| 데일리 리포트와 revision | 당시 분석과 근거 재현 |
| 명시된 기존 자료·별칭·호환 인덱스 | 기존 ID와 링크 유지 |
| 명시된 출처 설정·JSON schema·선언형 PM 규칙·문서 | 읽기 전용 계약·출처 설명 |
| manifest·파일 hash·공개 source ref·commit SHA | 동일 버전과 무결성 검증 |

`rules/pm/pm-selection-v3.json` 같은 선언형 규칙은 실행 코드와 구별한다.
반입된 `AGENTS.md`와 문서는 snapshot 안의 참고 자료다. 사내 루트 지침을
대체하거나 공개 지침에 사내 실행 권한을 부여하지 않는다.

## 반입하지 않을 자료

- `.github/` workflow와 공개 `dashboard/` 실행 코드.
- 수집·평가·배포용 `pipeline/`, `scripts/`, 테스트 등 실행 코드.
- 인증 정보, token, cookie, 계정 정보, 개인 식별자.
- 원문 캐시, checkpoint, lock, 실행 ledger, 비용·오류·운영 로그.
- 개인 Notion 문서, 메일, 비공개 조사 자료, 사내 PRD와 내부 분석.

허용된 경로에도 비밀값이나 개인 정보를 넣지 않는다. 사내 고유 평가와
공개 PM 평가는 별도 이름공간에 둔다. 사내 PRD, 평가, 로드맵과 의사결정
결과를 공개 저장소로 역동기화하지 않는다.

## 공개 버전 선택

- `main`: 소유자가 PR을 검토하고 merge한 버전.
- `work/browser-benchmark`: 에이전트가 검증한 후보. 소유자 승인과 다르다.

소비 환경에서 선택한 ref와 실제 반입 SHA를 함께 기록한다. 수집 성공과
소유자 승인 시각도 구별한다. 이 문서는 사내 스케줄이나 source branch를 변경하지 않는다.

## 반입 명령

아래 경로는 예시다. 신뢰할 수 있는 도구 설치, 공개 fetch 캐시, 사내
checkout을 각각 준비한다. Python 환경에는 `jsonschema`가 필요하다.
공개 Git 이력을 **별도 캐시로 fetch하는 것**은 허용한다. 그 이력을
사내 checkout에 merge하거나 사내 원격에 mirror push하지 않는다.

```sh
set -eu
trusted_tools=/opt/browser-benchmark-tools
public_cache=/srv/cache/browser-benchmark
company_checkout=/srv/company-repository
import_private=/srv/private/browser-benchmark-import
source_branch=main
source_ref="refs/remotes/origin/$source_branch"
managed="$company_checkout/vendor/browser-benchmark"
mkdir -p "$import_private"
candidate=$(mktemp -d "$import_private/candidate.XXXXXX")
package="$candidate/package"

git -C "$public_cache" fetch origin "$source_branch:$source_ref"
source_sha=$(git -C "$public_cache" rev-parse --verify "$source_ref^{commit}")
python "$trusted_tools/scripts/export_dataset.py" export \
  --repository "$public_cache" --ref "$source_sha" \
  --source-repository https://github.com/sangria-kim/browser-benchmark \
  --output "$package" > "$candidate/export-result.json"
manifest_sha=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["manifest_sha256"])' \
  "$candidate/export-result.json")
python "$trusted_tools/scripts/export_dataset.py" verify \
  --package "$package" --expected-commit "$source_sha" \
  --manifest-sha256 "$manifest_sha"
```

관리 경로가 아직 없으면 최초 한 번만 초기화한다. 빈 전용 경로를 사용한다.
사내 저장소 루트나 기존 사내 파일이 있는 경로를 지정하지 않는다.

```sh
python "$trusted_tools/scripts/export_dataset.py" init --managed "$managed"
```

모든 writer는 같은 private lock 경로를 사용한다. 반입부터 사내 commit까지
한 번에 한 writer만 실행한다.

```sh
python "$trusted_tools/scripts/export_dataset.py" import \
  --package "$package" --managed "$managed" --private-dir "$import_private" \
  --expected-commit "$source_sha" --manifest-sha256 "$manifest_sha"
snapshot=$(python "$trusted_tools/scripts/export_dataset.py" resolve --managed "$managed")
git -C "$company_checkout" add -- vendor/browser-benchmark
git -C "$company_checkout" diff --cached --stat
```

staged 변경이 관리 경로 안에만 있는지 확인한다. 사내 대시보드 검사를
`$snapshot`에 대해 실행한다. 사내 기본 브랜치 기반의 작업 브랜치에 자료
변경만 새 commit으로 작성하고 사내 PR 절차를 따른다. 공개 commit 자체를
사내 원격에 push하지 않는다. workflow 권한을 추가해서 전체 저장소 push를
우회하는 방법도 사용하지 않는다.

검증 실패 시 중단한다. importer는 hash·schema·참조·경로를 검사한 뒤
완성된 snapshot을 만들고 `current.json` 포인터를 원자적으로 교체한다.
실패 시 마지막 정상 자료와 사내 workflow·대시보드를 유지한다. 삭제도
새 snapshot 안의 자료 범위에만 반영한다. 사내 파일이나 이전 snapshot을
임의로 삭제하지 않는다. reader는 요청마다 포인터를 한 번만 읽는다.

실제 사내 인증, CI, 대시보드와 배포는 해당 환경에서 별도로 확인한다.
자세한 검증·복구 조건은 [반입 계약](internal-import-contract.md)을 따른다.
