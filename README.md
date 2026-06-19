# 📄 ARIES: Analog & RF Insight and Equation Summarizer

> **AI-Driven Information Extraction Pipeline Tailored for IC Design Engineers & Researchers**

ARIES는 Analog/RF 회로 설계자가 선행 연구 및 레퍼런스 논문을 분석할 때 소요되는 반복적이고 비효율적인 리딩 사이클을 혁신하기 위해 개발된 **지능형 정보 구조화 도구**입니다. 대량의 논문 PDF로부터 설계 핵심 수식, 변수 정의, 공정 제약 조건, 그리고 실전 디펜스 가이드라인까지 추출하여 시각적인 대시보드로 자동 빌드합니다.

---

## 💡 Motivation & Problem Statement

* **수식 전제 조건의 파편화:** Analog/RF 회로 설계(예: PLL, RF Front-end 등) 시, 여러 레퍼런스 논문에서 유사한 형태의 수식이 사용되더라도 적용된 CMOS 공정 노드, 동작 영역(Sub-threshold / Saturation), 입력 파워 레벨 등의 **전제 조건과 가정이 상이**합니다.
* **검증 리소스의 과다 소모:** 수식의 수학적 이해보다 해당 식의 유효 범위를 원문에서 일일이 찾아내고 비교 검증하는 과정에서 극심한 시간 왜곡과 병목이 발생했습니다.
* **해결책:** 본 엔지니어는 이 문제를 해결하고자 **LLM 구조화 파이프라인과 정밀 정제 엔진**을 결합하여, 설계자가 오직 "회로적 타당성 판단과 스펙 최적화"에만 집중할 수 있도록 돕는 ARIES를 개발했습니다.

---

## ✨ Key Features

* **LLM-Based Structural Parsing:** `Gemini-2.5-flash` 모델과 `Pydantic BaseModel`을 결합하여, 단순 텍스트 요약을 넘어 설계자가 지정한 정밀 스키마 규격으로 데이터를 강제 추출합니다.
* **Robust LaTeX Cleansing Engine (트러블슈팅 반영):** LLM이 수식을 분수 슬래시(`/`) 등으로 모호하게 출력하거나 기생 성분 기호가 깨지는 현상을 방지하기 위해, 내부 괄호 Depth 체크 및 정규식을 활용한 **`\frac` 포맷 복원 및 회로 변수 아래첨자(`V_{DD}`, `g_m`, `C_L`) 하드코딩 교정 엔진**을 탑재했습니다.
* **Deterministic File Caching:** 다중 파일 처리 시 중복 연산과 API 비용 낭비를 방지하기 위해 로컬 JSON 검증 디바이스 기반의 지능형 패스(Skip) 기능을 지원합니다.
* **Dual-View Dashboard Generation:**
  * **개별 논문 리포트:** MathJax 렌더링이 내장된 HTML 대시보드를 생성하여 핵심 수식, 물리적 직관, 실전 면접/디펜스 치트키 가이드를 시각화합니다.
  * **통합 비교 분석 매트릭스:** 폴더 내 모든 선행 연구들의 핵심 스펙과 대표 수식을 한눈에 교차 검증할 수 있는 통합 대시보드를 자동 빌드합니다.
* **Concurrency Path Stability:** 멀티스레딩 GUI 환경에서 파일 경로가 인버전되는 문제를 방지하기 위해 전역 디렉토리 제어 대신 **절대 경로 파싱 아키텍처**를 채택하여 구동 안정성을 극대화했습니다.

---

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Framework & GUI:** Tkinter, TTK Style Environment
* **AI & Parser Engine:** Google GenAI SDK (Gemini-2.5-flash), Pydantic v2
* **PDF Scraper:** PyPDF (Physical Buffer Sync Scan)
* **Frontend Rendering:** HTML5, CSS3, MathJax v3 (Dynamic Math Typeface)

---

## 📊 System Architecture & Data Flow

1. **PDF Text Stream Scanner:** `PyPDF` 버퍼 스캔을 통한 대용량 논문 원문 데이터 확보
2. **Strict Schema injection:** 시니어 IC 디자이너 관점의 프롬프트 인스트럭션 및 Pydantic 스키마 주입
3. **Regex Sub-Lexer Filter:** 수식 깨짐 방지를 위한 백슬래시 이스케이프 및 LaTeX 세척 세러피 가동
4. **HTML Dashboard Compiler:** 개별 및 통합 비교 분석 매트릭스 렌더링 및 파일 I/O 영속화

---

## 🚀 How It Works (Example)

### Input Area
```text
your_research_folder/
├── ISSCC_2024_PLL.pdf
├── JSSC_2023_RF_Frontend.pdf
└── [ARIES GUI Application Executed]
