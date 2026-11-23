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

신규 스케줄 연동 시 수집 명령에 `--daily-status`와 고정된 한국시간 오전 08:00 마감을 지정합니다. 동일 실행 재개에도 두 인수를 유지합니다. 기본 수집 및 기존 수동·백필 실행은 상태 파일을 만들지 않습니다.

```sh
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$RUN_ID" \
  --cutoff "$CUTOFF" --daily-status
python -m pipeline.run_daily --private-dir "$PRIVATE_STATE" --run-id "$RUN_ID" \
  --save-features "$PRIVATE_STATE/$RUN_ID/features.json"
```

분류를 끝내고 회귀 및 저장 경로 검증을 통과한 뒤 저장합니다. 이 모드의 분류 항목에 `change_kind`를 지정합니다. 실제 기능 추가·변경에는 `product_change`를 쓰고, 기능이 동일한 기존 항목의 공식 근거만 보강할 때는 `evidence_only`를 씁니다. 소스 본문이나 링크 변경만으로는 기능 변경이 아닙니다. 기능 변경 수는 분류행 수가 아닙니다.

이 모드의 비공개 분류 파일은 `decisions`와 `dispositions` 배열을 갖는 객체입니다. `decisions`에는 위 기능 분류와 `change_kind`를 사용합니다. `dispositions`에는 각 후보의 `source_id`, `source_item_id`, 최신 `revision_id`, `disposition`을 한 번씩 기록합니다. 결과는 `selected`, `excluded`, `unchanged` 중 하나입니다. `selected`인 후보만 기능 분류 행과 연결됩니다. 판정이 없거나 미해결인 후보가 하나라도 있으면 완료로 저장하지 않습니다. 후보가 있지만 모두 제외하면 `decisions`만 빈 배열입니다. 두 배열이 모두 비는 경우는 후보가 없는 날뿐입니다. 일반 수집의 기존 배열 형식은 그대로입니다.

활성 출처 전체를 확인하지 못했거나 검증을 마치지 못했으면 `--save-features` 대신 같은 실행에 `--record-incomplete`를 사용합니다. 이 단계는 상태 파일만 쓰고 후보를 보존합니다. `--allow-partial`로 완료 상태를 쓸 수 없습니다. 같은 날짜의 완료 상태는 미완료 재시도로 후퇴하지 않습니다. 완료본이 있으면 같은 날짜의 재실행은 기능 변경이나 건수 변경을 덮어쓰지 않습니다.

변경이 있는 완료 상태는 기능·근거와 같은 작업 트리 트랜잭션에 저장됩니다. GitHub에는 같은 PR에 올립니다. 0건이면 상태 파일만 올릴 수 있습니다. 진단 로그는 공개하지 않습니다. CI는 `python -m pipeline.daily_status`로 상태 파일을 검증합니다.
