# 📄 ARIES: Analog & RF Insight and Equation Summarizer

> **대학원 회로 설계 랩실에서 레퍼런스 논문 파헤치다가 화가나서 직접 만든 정보 추출 툴**

ARIES는 Analog/RF 회로 설계할 때 널려 있는 레퍼런스 논문들을 일일이 읽고, 수식 전제 조건 비교하느라 버려지는 아까운 리딩 시간을 줄이려고 만든 **실전형 데이터 구조화 툴**입니다. 논문 PDF만 던져 넣으면 핵심 설계 수식, 변수 정의, 공정 제약 조건, 면접용 디펜스 포인트까지 싹 뽑아서 깔끔한 HTML 대시보드로 묶어줍니다.

---

## 💡 개발 배경 (Motivation)

* **논문마다 제각각인 전제 조건:** 각종 프로젝트에서 설계할 때 논문들을 비교해 보면, 똑같이 생긴 수식인데도 공정 노드(28nm/55nm 등)나 bias 영역, 입력 파워 레벨 같은 전제 조건이 조금씩 다릅니다.
* **시간 낭비의 주범:** 수식 자체를 이해하는 것보다 "이 식이 대체 어떤 마진과 조건에서 성립하는가?"를 본문 속에서 일일이 찾아 비교하는 게 진짜 노가다였고, 시간도 제일 많이 뺏겼습니다.
* **해결책:** "귀찮은 반복 작업은 툴한테 맡기고, 엔지니어는 회로적 타당성 판단이랑 시뮬레이션 튜닝에만 집중하자"는 생각으로 퇴근길에 짬짬이 빌드했습니다.

---

## 🔥 핵심 기능 (Features) & 트러블슈팅 기록

* **Pydantic 스키마 기반 정밀 파싱:** `Gemini-2.5-flash` API에 Pydantic 스키마를 강제 주입해서, AI가 헛소리(할루시네이션) 하거나 대충 요약하지 못하도록 원하는 규격으로만 데이터가 튀어나오게 묶었습니다.
* **LaTeX 수식 깨짐 방지 엔진 (가장 삽질한 부분):** AI가 분수를 슬래시(`/`)로 뱉거나 기생 소자 기호(`V_DD`, `g_m`, `C_L`) 언더바를 빼먹어서 렌더링이 깨지는 문제가 있었습니다. 괄호 깊이(Depth) 체크랑 정규식 필터를 직접 짜 넣어서, 무조건 깔끔한 `\frac` 포맷이랑 아래첨자로 자동 변환되게 수식 세척 기능을 구현했습니다.
* **멀티스레딩 절대 경로 디버깅:** 여러 논문을 한 번에 일괄 처리(Batch)할 때 GUI 스레드 상에서 파일 경로가 인버전되거나 꼬여서 엉뚱한 폴더에 저장되는 버그가 있었습니다. 전역 디렉토리 제어하는 편법 대신 아예 절대 경로 파싱 아키텍처로 뜯어고쳐서 구동 안정성을 잡았습니다.
* **지능형 로컬 캐싱:** 똑같은 논문 또 돌려서 API 비용 날리는 짓을 막으려고, 폴더 내에 이미 파싱된 `_analysis.json` 파일이 있으면 알아서 Skip하고 넘어가는 고속 패스 기능을 넣었습니다.
* **두 가지 맛 대시보드 빌드:** 
  * **개별 리포트:** MathJax 렌더링을 내장해 수식이 예쁘게 표현되는 HTML 페이지 (물리적 직관, 심층 디펜스 가이드 포함).
  * **통합 비교 분석표:** 폴더 내 모든 논문의 타깃 스펙이랑 핵심 수식만 한눈에 가로로 쫙 비교할 수 있는 마스터 대시보드를 생성합니다.

---

## 🛠️ 사용 기술 (Tech Stack)

* **언어:** Python 3.10+
* **UI 부문:** Tkinter, TTK 스타일 위젯
* **AI & 파서:** 구글 GenAI SDK (`gemini-2.5-flash`), Pydantic v2
* **PDF 처리:** PyPDF (물리 버퍼 스캔 방식)
* **프론트엔드:** HTML5, CSS3, MathJax v3 (수식 폰트 렌더링용)

---

## 🚀 실제 돌아가는 구조 (Example)
<div align="center">

<!-- 1. 초기 화면 -->
<img width="1032" height="729" alt="image" src="https://github.com/user-attachments/assets/f2491e19-93c2-4026-9f76-d0744f474873" />
<br>
<em>📷 [초기 화면] 깔끔한 GUI 레이아웃 및 Gemini API 연동 세팅</em>

<br><br>

<!-- 2. 폴더 설정 -->
<img width="1032" height="730" alt="image" src="https://github.com/user-attachments/assets/0670be44-4b74-4d46-91f9-71df704f25b4" />
<br>
<em>📂 [폴더 설정] 논문 PDF가 모여있는 대상 디렉토리 지정 및 캐시 무결성 검증</em>

<br><br>

<!-- 3. 구동 화면 -->
<img width="1029" height="730" alt="image" src="https://github.com/user-attachments/assets/821c476e-b500-422f-84be-6bfbc8a7b8e5" />
<br>
<em>⚡ [구동 화면] 멀티스레딩 기반 실시간 텍스트 스캔 및 Gemini AI 구조화 파이프라인 가동</em>

<br><br>

<!-- 4. 결과 화면 -->
<img width="885" height="916" alt="image" src="https://github.com/user-attachments/assets/bc6006cd-c6ba-439f-8e67-af9959363a81" />
<img width="896" height="892" alt="image" src="https://github.com/user-attachments/assets/6b9d60d7-9a21-4274-9a9f-4a6bce11ab93" />
<img width="1031" height="730" alt="image" src="https://github.com/user-attachments/assets/9f8b6b05-56b5-4143-8534-f42c672712bf" />
<img width="1864" height="826" alt="image" src="https://github.com/user-attachments/assets/49a4b4f0-daef-423e-a248-c8d455efd1ae" />
<br>
<em>🏆 [결과 화면] MathJax 수식 렌더링 및 면접 디펜스 가이드가 포함된 통합 HTML 대시보드 빌드 완료</em>

</div>


### 논문 폴더 상태 (Input)
```text
my_circuit_papers/
├── ISSCC_2024_PLL.pdf
├── JSSC_2023_RF_Frontend.pdf
└── [여기서 ARIES 프로그램 켜고 폴더 선택 후 시작 클릭]

my_circuit_papers/
├── ISSCC_2024_PLL_analysis.json  <-- 중복 연산 방지용 캐시
├── ISSCC_2024_PLL_dashboard.html <-- 수식 정리된 개별 리포트
├── JSSC_2023_RF_Frontend_analysis.json
├── JSSC_2023_RF_Frontend_dashboard.html
└── __통합_비교_분석표_대시보드.html          <-- 🏆 이 프로젝트의 하이라이트 (선행연구 비교표)
