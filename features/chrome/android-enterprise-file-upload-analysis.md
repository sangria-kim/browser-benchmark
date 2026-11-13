# Chrome Android 기업 파일 업로드 검사 설정 실험

- Feature ID: `chrome-android-enterprise-file-upload-analysis`
- 사건: `chrome-android-enterprise-file-upload-analysis-source-20261112`
- 업무: mobile; AI 관련: false
- 현재 상태: source-main 실험 관찰, P1 / conditional. 설치본 노출·실기 동작 미확인.
- 우선순위 이유: 관리되는 파일 업로드의 허용·차단과 데이터 처리 조건에 직접 연결되므로 정책·안내·오류 흐름을 우선 확인할 가치가 있습니다.
- [사건 JSON](../../data/events/chrome-android-enterprise-file-upload-analysis-source-20261112.json) · [enable-file-attached-enterprise-scan-on-clank](../../experiments/chrome/enable-file-attached-enterprise-scan-on-clank.md)

## 확인된 변화

Android에서 파일 선택기 또는 drag-and-drop으로 첨부하는 파일의 기업 콘텐츠 검사 flag를 등록합니다. OnFileAttachedEnterpriseConnector 정책이 설정된 경우에 적용되며 기본 비활성입니다. 관리 정책이 적용된 테스트 환경을 전제로 합니다. OnFileAttachedEnterpriseConnector가 설정되어야 하며 kEnableFileAttachedEnterpriseScanOnClank는 IS_ANDROID에서 FEATURE_DISABLED_BY_DEFAULT입니다. 소비자 전체의 파일이 자동 전송·검사된다는 뜻이 아닙니다.

이 커밋은 about_flags, flag-metadata, flag_descriptions, histogram enum만 변경합니다. 기존 검사 feature를 chrome://flags에서 설정하게 하는 등록-only 사건이며 검사 구현 확대나 기본 활성화가 아닙니다. 파일 선택기/drag-and-drop 첨부가 대상이라는 설명만 확인했습니다. 실제 전송 여부·서버 대상·검사 지연·기기별 지원은 확인하지 않았습니다.

- 소스 commit 시각: 2026-11-12T20:05:20Z.
- 근거 확인일: 2026-11-13 KST. 발표일·실제 적용일은 미확인.
- 소스 등록·삭제는 단독으로 출시·철회 증거가 아니다.

## PM 비교 질문

비교 대상은 같은 플랫폼·조건의 Chrome과 삼성 브라우저다. 삼성 브라우저의 해당 기능 지원 여부는 먼저 확인하며 미지원이면 대체 흐름 또는 미지원으로 기록한다.

동일한 관리 정책 아래 파일 첨부의 검사 상태와 차단 이유를 얼마나 명확히 알리며, 사용자는 어떤 조치로 작업을 완료하는가?

## 동일 조건과 재현 절차

같은 플랫폼·소스 또는 제품 버전·계정·정책·네트워크·입력 자료를 고정한다. 비교 브라우저의 해당 과제 지원 여부부터 확인하며 삼성 브라우저의 지원 여부나 내부 계획은 추정하지 않는다.

1. 테스트용 관리 환경과 비민감 샘플 파일을 준비한다.
2. 대상 정책과 flag가 실제 설치본에 노출되는지 먼저 확인한다.
3. 허용·차단·검사 지연 조건에서 파일 선택기 첨부를 비교한다.
4. 기기가 지원하면 drag-and-drop 경로를 같은 조건으로 비교한다.

## 지표와 완료 기준

- 검사 상태 표시 여부
- 차단 이유 이해 가능성
- 첨부 완료 시간
- 오류 후 복구 조작 수
- 지원 입력 경로 간 일관성

완료 기준: 정책 없는 대조군과 정책 적용군의 허용·차단·지연 결과를 기록하고 비민감 샘플로만 재현한다.

아직 위 시험을 수행하지 않았다. 한국 제공·한국어 지원·기기·계정별 실제 접근 조건은 unknown이다. 소스 관찰, 설치본 노출, 동작 검증을 별도로 기록한다.

## 공식 근거

- [Add a chrome://flags entry for file upload content analysis on Android](https://github.com/chromium/chromium/commit/ad71b47248b1e71be1385c7fd411d8eccee9c1ff)
- [Android file attachment enterprise scan 기본값](https://github.com/chromium/chromium/blob/ad71b47248b1e71be1385c7fd411d8eccee9c1ff/components/enterprise/connectors/core/features.cc)
