# Chrome enable-file-attached-enterprise-scan-on-clank

- Flag ID: `enable-file-attached-enterprise-scan-on-clank`
- 연결 기능: [Chrome Android 기업 파일 업로드 검사 설정 실험](../../features/chrome/android-enterprise-file-upload-analysis.md)
- 사건: [chrome-android-enterprise-file-upload-analysis-source-20261112](../../data/events/chrome-android-enterprise-file-upload-analysis-source-20261112.json)
- 상태: source-main flag 등록 관찰. 출시·설치본 노출·실기 미확인.
- 플랫폼: kOsAndroid이며 IS_ANDROID build 조건 안에 있다.
- 2026-11-12 source commit: [ad71b47248b1e71be1385c7fd411d8eccee9c1ff](https://github.com/chromium/chromium/commit/ad71b47248b1e71be1385c7fd411d8eccee9c1ff)

관리 정책이 적용된 테스트 환경을 전제로 합니다. OnFileAttachedEnterpriseConnector가 설정되어야 하며 kEnableFileAttachedEnterpriseScanOnClank는 IS_ANDROID에서 FEATURE_DISABLED_BY_DEFAULT입니다. 소비자 전체의 파일이 자동 전송·검사된다는 뜻이 아닙니다.

이 커밋은 about_flags, flag-metadata, flag_descriptions, histogram enum만 변경합니다. 기존 검사 feature를 chrome://flags에서 설정하게 하는 등록-only 사건이며 검사 구현 확대나 기본 활성화가 아닙니다. 파일 선택기/drag-and-drop 첨부가 대상이라는 설명만 확인했습니다. 실제 전송 여부·서버 대상·검사 지연·기기별 지원은 확인하지 않았습니다.

한국 제공·한국어 지원은 unknown이다. 소스 등록은 최초 기능 도입이나 일반 사용자 활성화를 입증하지 않는다.
