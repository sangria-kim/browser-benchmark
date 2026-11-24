# 브라우저 기능 수집과 저장

Python 3.9 이상과 `schemas/requirements.txt`를 설치합니다. 브라우저별 조사 대상은 [공식 출처 설정](../config/sources.yml)에서 관리합니다.

1. 저장소 밖의 전용 작업 디렉터리에 업데이트 후보를 수집합니다. `--source`를 생략하면 활성 출처 전체를 조사합니다.

   ```sh
   python -m pipeline.collect --private-dir "$PRIVATE_RUN" --source firefox-beta
   ```

2. 수집 에이전트가 `$PRIVATE_RUN/work/candidates/<source-id>.json`에 있는 항목을 [기능 기준](../docs/collection-policy.md)에 따라 분류합니다. 기능으로 확인한 항목만 아래 형식의 JSON 배열에 넣고 작업 디렉터리의 `features.json`으로 저장합니다. ID는 후보의 `source_item_id`와 마지막 `revisions` 항목의 `revision_id`를 사용합니다. 한 원문이 여러 기능을 설명하면 각 기능 키에 같은 출처 항목과 리비전을 지정합니다. 같은 기능을 다시 관찰하면 카탈로그에 있는 해당 브라우저의 `canonical_key`를 사용합니다.

   공개 미리보기(`evidence.excerpt`)가 220자이면 기능별로 `evidence_quote`를 지정합니다. 긴 항목은 비공개 후보의 `classification_text`에서 해당 기능을 설명하는 연속된 구절을 최대 1,200자까지 그대로 복사합니다. 더 짧은 항목은 인용을 생략하면 미리보기 전체를 사용합니다. 이전 실행의 후보에 긴 본문이 없으면 새 실행으로 다시 수집해 뒷부분을 인용합니다.

   ```json
   [
     {
       "source_item_id": "<source_item_id>",
       "revision_id": "<revision_id>",
       "canonical_key": "shared-tab-groups",
       "title": "탭 그룹 공유",
       "evidence_quote": "You can now share tab groups."
     }
   ]
   ```

3. 분류한 기능과 공식 근거를 저장합니다. 이 단계는 수집한 원문 버전으로 오프라인에서 실행됩니다. 빈 배열도 기존 카탈로그와 근거를 검증합니다. 참조가 끊어지면 후보를 보존하므로 근거를 복구한 뒤 다시 저장할 수 있습니다.

   ```sh
   python -m pipeline.collect --private-dir "$PRIVATE_RUN" --save-features "$PRIVATE_RUN/features.json"
   ```

수집 종료 코드 2는 요청한 출처 일부를 확인하지 못했다는 뜻입니다. 그 상태를 기능 변화 없음으로 해석하지 않습니다. 재시도할 때는 같은 디렉터리, `--resume`을 사용합니다. 원래 마감 시각과 출처를 재사용하며, 첫 실행에 제공한 메타데이터 입력도 다시 지정합니다. 실패한 출처의 기존 기능은 보존합니다.

## 수집 기간과 재개

기존 `pipeline.run_daily` 호출은 일일 모드를 선택합니다. `--cutoff`에는 예정 시각과 시간대를 지정합니다. 일일 하한은 서울 시각으로 마감 30일 전 같은 시각입니다. 양끝을 포함합니다. `config/sources.yml`의 `baseline.daily_window_days`는 수집 기간입니다. `pipeline.collect`의 기본 모드는 수동입니다.

| 모드 | 범위 | 저장 |
| --- | --- | --- |
| `daily` | 최근 30일 | 기존 기능 분류 배열을 받습니다. `--daily-status`로 시작한 07:00 실행은 아래의 전수 판정 규칙을 사용합니다. |
| `weekly_reconcile` | 정책 시작일 00:00 KST부터 마감까지 | 모든 활성 출처와 후보의 최종 판정이 필요합니다. 결과는 비공개 실행 기록 및 검증된 기능과 근거에 저장합니다. |
| `manual` | 기본 최근 30일. `--source`와 `--since`로 대상과 하한 지정 | 별도 실행 ID와 분류 배열을 사용합니다. |
| `legacy` | 기존 정책 시작일부터 전체 수집 | 전환 전 수집 범위로 복귀할 때 사용합니다. 기본 분류 배열을 받습니다. |

주간 작업을 시험할 때는 새 ID와 주간 마감을 명시합니다. 아래 명령은 일회성 실행입니다.

```sh
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$WEEK_ID" \
  --mode weekly_reconcile --cutoff "$WEEK_CUTOFF"
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$WEEK_ID" \
  --save-features "$PRIVATE_STATE/$WEEK_ID/classification.json"
```

주간 분류 파일은 아래 일일 예시와 같은 `decisions`와 `dispositions` 배열을 사용합니다. 저장에는 모든 후보의 최종 판정이 필요합니다. `collection_complete`는 요청한 출처의 수집 결과입니다. 분류·저장까지 마치면 비공개 `feature-run.json`의 상태가 `saved`가 됩니다. 일부 출처만 진단한 주간 실행은 전체 대조로 저장할 수 없습니다. 기간이 30일 넘게 비면 주간 대조나 명시한 수동 기간으로 보충합니다. 과거 일일 상태의 날짜는 그대로 유지됩니다.

공식 시각은 시간대 오프셋을 적용합니다. 날짜만 있는 항목은 양쪽 경계일 전체를 포함하며 공개 근거에 일 단위 정밀도를 유지합니다. 날짜가 없으면 미상으로 유지합니다. 목록의 날짜는 상세의 정확한 시각과 다를 수 있어 경계 주변 상세를 읽습니다. 명시된 공식 수정일이 있으면 오래된 문서의 최근 변경도 확인합니다. 마감 이후 개정된 본문만 있으면 해당 출처는 미완료입니다. 과거 공개일만 알 수 있는 글은 주간 대조가 다시 확인합니다. 주간 발견 시점은 근거의 관측 시각에, 출처의 공식 날짜는 해당 날짜 필드에 기록됩니다.

비공개 실행 기록에 모드, 실행 ID, 코드·기준 커밋, 등록 설정과 보충 입력의 해시, 하한, 마감, 출처별 상태와 후보 파일 해시가 남습니다. 재개는 같은 입력만 허용합니다. 완료한 출처는 후보 파일의 해시를 확인합니다. 중단된 출처는 무결성을 확인한 응답으로 다시 파싱합니다. 가변 목록의 페이지 내용이 바뀌어 이어 읽을 수 없으면 새 ID로 다시 시작합니다. 이전 버전의 미완료 실행에는 새 검증 정보가 없으므로 새 ID로 수집합니다. 새 ID는 응답을 새로 가져옵니다.

출처별 `baseline.source_attempt_seconds`의 기본값은 900초입니다. 요청 사이와 항목 처리 중에 시간을 확인합니다. 진행 중인 HTTP 요청에는 기존 전송 시간 제한과 재시도 규칙이 적용됩니다. 한 출처에서 시간이나 페이지·문서 예산이 끝나면 나머지 출처를 조사합니다. 종료 코드 2이면 비공개 `source_results`의 오류와 남은 범위를 확인합니다. 프로세스를 강제 종료하면 상태가 `collecting`에 머물며 같은 마감으로 재개할 수 있습니다.

저장소 잠금은 수집 중에도 유지합니다. 겹치는 실행은 잠금 오류 후 같은 예정 시각으로 다시 시도합니다. 수집 후 다른 실행이 먼저 저장하면 저장기가 현재 근거와 카탈로그를 다시 읽습니다. 같은 리비전은 최초 저장된 관측을 유지합니다. 서로 다른 이력 또는 일일 상태용 기준 카탈로그가 충돌하면 새로 수집·분류합니다.

## 작업 공간과 일일 실행

각 수집에는 새 비공개 디렉터리를 지정합니다. 전체 후보와 응답 캐시는 분류하는 동안 `work/`에 머뭅니다. 분류 파일은 이 폴더 밖에 둡니다. 기능과 근거를 검증하고 저장하면 수집기가 자신의 `work/`를 정리합니다. 빈 선정 배열도 작업을 끝냅니다. 실행 상태 파일과 직접 만든 분류 파일은 남습니다. 부분 수집을 마감할 때는 저장 명령에 `--allow-partial`을 추가합니다. 실패한 저장에는 후보와 복구 자료가 남습니다.

일일 실행도 같은 경로를 사용합니다. 아래 예에서 후보는 `$PRIVATE_STATE/$RUN_ID/work/candidates/`에 있습니다.

```sh
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$RUN_ID"
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$RUN_ID" \
  --save-features "$PRIVATE_STATE/$RUN_ID/features.json"
```

이전 형식의 작업 디렉터리는 보존합니다. 이 명령으로 전환할 때는 새 실행 ID를 사용합니다. 기존 외부 스케줄러의 호출 인수는 운영 환경에서 맞춥니다. 저장 후에는 [저장소 PR 절차](../AGENTS.md)를 따릅니다.

ChromeStatus의 예전 출처에는 당시 출시 단계와 플랫폼별 지원 버전이 빠져 있습니다. 수집기는 기존 설명과 일치하는 항목의 첫 관측값을 비공개 비교 기준으로 보관합니다. 이때 공개 기능 이력은 그대로 유지합니다. 이후 공식 출시 단계 또는 데스크톱·Android·iOS·WebView 지원 버전이 바뀌면 해당 근거를 분류 후보로 전달합니다. 수정 시각만 바뀌면 건너뜁니다. 일일 실행에는 같은 체크아웃과 같은 `$PRIVATE_STATE`를 사용합니다. 비교 기준은 이 경로의 `.browser-benchmark-comparison-<uid>/`에 있으며 실행별 원문 정리 후에도 유지됩니다.


## 일일 수집 상태 파일

신규 스케줄 연동 시 수집 명령에 `--daily-status`와 한국시간 07:00:00 정각의 마감을 지정합니다. 같은 시점의 UTC 입력도 허용합니다. 공개 파일에는 한국 날짜와 `+09:00` 마감을 기록합니다. 동일 실행 재개에도 두 인수를 유지합니다. 기본 수집 및 기존 수동·백필 실행은 상태 파일을 만들지 않습니다.

```sh
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$RUN_ID" \
  --cutoff "$CUTOFF" --daily-status
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$RUN_ID" \
  --save-features "$PRIVATE_STATE/$RUN_ID/features.json"
```

분류를 끝내고 회귀 및 저장 경로 검증을 통과한 뒤 저장합니다. 이 모드의 분류 항목에 `change_kind`를 지정합니다. 실제 기능 추가·변경에는 `product_change`를 쓰고, 기능이 동일한 기존 항목의 공식 근거만 보강할 때는 `evidence_only`를 씁니다. 소스 본문이나 링크 변경만으로는 기능 변경이 아닙니다. 최상위 `collected_feature_count`는 이 실행에서 채택한 고유 기능 수입니다. 기능마다 한 번만 세며, 근거 보강만 한 기능도 포함합니다. 제외·미변경으로 판정한 후보는 세지 않습니다. `change_count`는 그중 실제 기능 추가·변경 수입니다.

이 모드의 비공개 분류 파일은 `decisions`와 `dispositions` 배열을 갖는 객체입니다. `decisions`에는 위 기능 분류와 `change_kind`를 사용합니다. `dispositions`에는 각 후보의 `source_id`, `source_item_id`, 최신 `revision_id`, `disposition`을 한 번씩 기록합니다. 결과는 `selected`, `excluded`, `unchanged` 중 하나입니다. `selected`인 후보만 기능 분류 행과 연결됩니다. 판정이 없거나 미해결인 후보가 하나라도 있으면 완료로 저장하지 않습니다. 후보가 있지만 모두 제외하면 `decisions`만 빈 배열입니다. 두 배열이 모두 비는 경우는 후보가 없는 날뿐입니다. 일반 수집의 기존 배열 형식은 그대로입니다.

활성 출처 전체를 확인하지 못했거나 검증을 마치지 못했으면 `--save-features` 대신 같은 실행에 `--record-incomplete`를 사용합니다. 이 단계는 두 건수를 `null`로 기록하고 후보를 보존합니다. `--allow-partial`로 완료 상태를 쓸 수 없습니다. 같은 날짜의 완료 상태는 미완료 재시도로 후퇴하지 않습니다. 완료본이 있으면 같은 날짜의 재실행은 기능 변경이나 건수 변경을 덮어쓰지 않습니다.

기존 08:00 공개 파일은 CI와 소비자가 계속 읽습니다. 날짜별 파일은 하나이며, 기존 파일이 미완료여도 다른 마감으로 대체할 수 없습니다. 아직 게시하지 않은 08:00 실행은 새 코드로 재개하거나 저장할 수 없습니다. 07:00 수집에는 새 실행 ID를 사용합니다. 이미 게시한 08:00 실행은 같은 분류로 저장을 재시도해 비공개 정리를 마칠 수 있습니다.

변경이 있는 완료 상태는 기능·근거와 같은 작업 트리 트랜잭션에 저장됩니다. GitHub에는 같은 PR에 올립니다. 새 기능·근거 파일이 없으면 상태 파일만 올립니다. 진단 로그는 공개하지 않습니다. CI는 `python -m pipeline.daily_status`로 상태 파일을 검증합니다.
