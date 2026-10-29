# Browser Benchmark

Chrome 실험 기능과 Chrome·Edge·Firefox의 새 기능 및 주요 동작 변경을 공개 공식 자료로 추적하는 아카이브입니다. Windows와 Android를 우선하며, 제품 비교와 재현 가능한 벤치마크 후보를 기록합니다.

## 현재 상태

저장소 및 운영 지침 초기화 완료. 실제 보고서 이관, 수집 실행 및 dots 자동화 연결은 아직 완료되지 않았습니다. 이 저장소 자체에는 예약 실행 기능이 없습니다.

## 읽기 전용 사용

```sh
git clone https://github.com/sangria-kim/browser-benchmark.git
cd browser-benchmark
git pull --ff-only
```

사내에서는 clone/pull로 열람합니다. 로컬 검토 자료는 저장소 밖에 보관하고 외부로 push하지 않습니다. 문서는 Markdown으로 읽을 수 있으며 사내 서버나 Notion 접속 없이 보관된 내용을 열람할 수 있습니다. 외부 출처 링크는 별도 인터넷 접근이 필요합니다.

## 저장 구조

| 경로 | 내용 |
| --- | --- |
| `releases/<browser>/<version>/README.md` | 버전별 변경 요약 및 기능 문서 링크 |
| `features/<browser>/<feature-id>.md` | 버전 간 기능 이력 |
| `experiments/chrome/<flag-id>.md` | Chrome flag 관찰 및 검증 상태 |
| `data/events/<event-id>.json` | 구조화된 변경 사건 |
| `reports/YYYY-MM-DD.md` | Asia/Seoul 날짜별 의미 있는 변화 |
| `assets/` | 공개 가능한 이미지, 상대 경로로 참조 |

위 경로는 실제 데이터 발생 시 생성합니다. 빈 보고서나 가짜 샘플 결과는 만들지 않습니다.

## 운영 문서

- [수집 및 게시 지침](docs/collection-policy.md)
- [보고서 템플릿](templates/report.md)

## 공개 범위

공개된 제품 정보와 그에 대한 분석만 게시합니다. 사내 데이터, 비공개 의견·평가, 개인정보, 이메일 주소·메시지 ID·계정 연결 ID, 인증 정보는 저장하지 않습니다. 메일 전송 및 실행 상태는 비공개 실행 환경에서 관리합니다. 제3자 원문은 링크와 필요한 최소 인용으로 출처를 표시합니다.
