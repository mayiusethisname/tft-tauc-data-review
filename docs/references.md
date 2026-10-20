# 참고한 사례와 적용한 방식

조사일: 2026-10-20. 아래 프로젝트의 문서와 실행 안내를 직접 확인하고, 이번 프로젝트에 필요한 구성만 적용했습니다.

## 공개 분석 프로젝트

| 참고 사례 | 확인한 구성 | 이 프로젝트에 적용 |
| --- | --- | --- |
| [Luke Barousse · SQL Project Data Job Analysis](https://github.com/lukebarousse/SQL_Project_Data_Job_Analysis) | 분석 질문을 먼저 제시하고 질문별 쿼리와 결과를 연결 | 목적을 README 앞에 두고, 확인할 문제별로 오류 사례 문서를 구성 |
| [Adithya · Power BI Portfolio 2](https://github.com/adithyasingapore/portfolio_2-power_bi) | 실제 전처리 내용을 설명한 뒤 완성 화면과 데이터 출처를 제시 | 파일을 어떻게 바꿨는지, 그래프에서 무엇을 확인하는지, 대조 원본이 무엇인지 연결 |
| [CEA-MetroCarac · Fitspy](https://github.com/CEA-MetroCarac/fitspy) | 스펙트럼 피팅 GUI를 이미지로 보여주고 예제·실행법·상세 문서를 연결 | 실제 곡선 그림을 README에 넣고, 실행법과 계산 설명을 나누어 연결 |

## 문서와 도움말 지침

- [GitHub · About READMEs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes): 프로젝트가 하는 일, 시작 방법과 도움받을 문서를 앞에서 찾을 수 있게 했습니다. 저장소 안 링크는 상대 경로를 사용합니다.
- [Google · READMEs](https://google.github.io/styleguide/docguide/READMEs.html): 최상위 README를 짧은 안내로 두고 디렉터리의 역할과 상세 문서로 연결했습니다.
- [W3C · Tooltip pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tooltip/): 마우스뿐 아니라 키보드 초점에서도 설명이 열리고 Esc로 닫히게 했습니다. 도움말 위에 커서를 옮겨도 읽을 수 있게 유지합니다.

## 물질 설명의 근거

- [삼성디스플레이 · 디스플레이의 보이지 않는 손 TFT](https://news.samsungdisplay.com/6571): 채널 구조, a-Si와 LTPS의 배열·이동도 차이 설명을 참고했습니다.
- [LG Display · Thin-Film Transistor](https://news.lgdisplay.com/en/2022/06/display-101-12-thin-film-transistors/): TFT 재료인 a-Si·LTPS·산화물의 기본 구분을 확인했습니다.
- [Nomura et al., Nature 432, 488–492 (2004)](https://www.nature.com/articles/nature03090): 비정질 산화물 TFT의 재료 설명을 참고했습니다.
- [Sharp · IGZO](https://global.sharp/igzo/): IGZO를 이루는 원소와 디스플레이 적용 설명을 확인했습니다. 제조사 제품의 성능 수치는 이 실측 파일의 결과에 대입하지 않았습니다.

## 적용 범위

외부 프로젝트의 코드를 가져오거나 디자인 파일을 복제하지 않았습니다. 문서의 순서, 예제와 근거를 연결하는 방식, 도움말 동작을 참고했습니다. 이 저장소의 계산값과 그림은 포함된 실측 자료와 분석 코드에서 나옵니다.
