# 브라우저 기능 수집과 저장

Python 3.9 이상과 `schemas/requirements.txt`를 설치합니다. 브라우저별 조사 대상은 [공식 출처 설정](../config/sources.yml)에서 관리합니다.

1. 저장소 밖의 전용 작업 디렉터리에 업데이트 후보를 수집합니다. `--source`를 생략하면 활성 출처 전체를 조사합니다.

   ```sh
   python -m pipeline.collect --private-dir "$PRIVATE_RUN" --source firefox-beta
   ```

2. 수집 에이전트가 `$PRIVATE_RUN/work/candidates/<source-id>.json`에 있는 항목을 [기능 기준](../docs/collection-policy.md)에 따라 분류합니다. 기능으로 확인한 항목만 아래 형식의 JSON 배열에 넣고 작업 디렉터리의 `features.json`으로 저장합니다. ID는 후보의 `source_item_id`와 마지막 `revisions` 항목의 `revision_id`를 사용합니다. 같은 기능을 다시 관찰하면 카탈로그에 있는 해당 브라우저의 `canonical_key`를 사용합니다.

   ```json
   [
     {
       "source_item_id": "<source_item_id>",
       "revision_id": "<revision_id>",
       "canonical_key": "shared-tab-groups",
       "title": "탭 그룹 공유"
     }
   ]
   ```

3. 분류한 기능과 공식 근거를 저장합니다. 이 단계는 수집한 원문 버전으로 오프라인에서 실행됩니다. 빈 배열은 기존 자료를 그대로 유지합니다.

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
