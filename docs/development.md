# 개발과 배포

## 폴더

```text
README.md              프로젝트 소개와 실행
index.html             세 단계 작업 화면
web/                   화면 동작, 그래프, 도움말, 스타일
analysis/              기존 계산·입력 모듈과 추가 진단
analysis_service.py    데모·업로드 공통 분석
examples.py            실측 목록과 오류 복사본 생성
samples/               실측 발췌 CSV·출처·해시
docs/                  사용법·계산·사례·참고 자료와 그림
tests/                 계산·입력·브라우저 동작 확인
validation/            기존 평가 집계
api/                   Vercel Python 진입점
run.py                 표준 라이브러리 로컬 서버
```

## 실행

```bash
python run.py --port 8765
```

화면과 API를 함께 실행합니다. HTML 파일을 단독으로 열면 분석 API를 사용할 수 없습니다.

## 구성과 구현 범위

기존 프로젝트의 TFT·Tauc 계산을 별도 공개 폴더로 옮긴 뒤, 예제와 업로드를 같은 경로로 연결하고 검토 화면과 입력 점검을 더했습니다.

| 구분 | 파일과 역할 |
| --- | --- |
| 이어온 계산 | `profile_8week.py`, `tauc_analysis.py`: 회귀·이동도·Vth·Tauc 변환과 구간 탐색 |
| 입력 점검 | `tft_file_intake.py`, `tauc_file_intake.py`, `diagnostics.py`: 필수 셀·조건·격자·오류 위치 |
| 공통 분석 | `analysis_service.py`: 예제/업로드 연결, 실제 조건 기록, 계산량·오류 응답 |
| 작업 화면 | `web/`: 그래프 조작, 후보 비교와 근거, 도움말, 검토 기록 |
| 데이터 재현 | `examples.py`, `samples/`, `tools/verify_sources.py`: 실측 발췌, 오류 복사본, 독립 원자료 대조 |

## 동작 확인

프로젝트 폴더에서 실행합니다.

```bash
python -m unittest discover -s tests -p "test_*.py" -q
node tests/test_review_state.cjs
python tools/audit_public_copy.py
```

원본 파일을 보관한 환경에서는 다음 명령으로 발췌본을 대조합니다. 경로는 보관 위치에 맞게 지정합니다. 분석 모듈을 불러오지 않고 signed 숫자쌍과 양쪽 파일의 해시를 확인합니다.

```bash
python tools/verify_sources.py --tft-dir ./original/TFT --uvvis-dir ./original/UVVis
```

JSON 업로드의 config에는 실제 사용할 재료·W/L과 `conditions_confirmed: true`가 필요합니다. 이 값은 사용자가 화면에서 조건을 확인한 뒤 전송합니다. Tauc는 선택한 고정 실험 프로파일과 동일한 조건을 확인합니다. 예제 경로는 명시된 예제 프로파일을 사용합니다.

브라우저 확인은 개발 환경에 Playwright와 Chrome 또는 Edge가 있을 때 실행합니다.

```bash
python tests/browser_smoke.py
```

다른 환경은 PORTFOLIO_BROWSER 환경변수로 브라우저 실행 파일을 지정할 수 있습니다. 화면 캡처는 실행 결과에 표시되는 임시 폴더에 저장됩니다.

## Vercel 구성

이 폴더를 프로젝트 루트로 연결하는 구성을 `vercel.json`과 `api/index.py`에 두었습니다. 서버 함수에는 분석 모듈과 샘플 CSV를 함께 포함합니다. 실제 배포 URL은 배포 후 README에 추가합니다.

원본 파일 크기는 3 MB 이하입니다. Base64 전송 크기와 함수 본문 제한을 고려한 설정입니다. [Python API 경로](https://vercel.com/docs/functions/runtimes/python/api-directory), [함수 제한](https://vercel.com/docs/functions/limitations)

## 그림

README와 사례 문서의 SVG는 실제 브라우저에서 렌더링한 그래프를 내보낸 것입니다. 별도의 가상 곡선이나 수기로 옮긴 좌표를 사용하지 않습니다.
