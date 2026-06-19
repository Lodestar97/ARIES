import base64
import json
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import webbrowser
from google import genai
from pydantic import BaseModel, Field
from pypdf import PdfReader


# =====================================================================
# [Data Schema] 데이터 파싱 및 JSON 매핑을 위한 Pydantic 구조정의
# =====================================================================

class VariableDetail(BaseModel):
    variable_name: str = Field(description="수식에 사용된 변수 기호 (예: g_m, V_ov, C_L)")
    definition: str = Field(description="해당 변수의 의미 및 설계 관점에서의 정성적/정량적 설명")

class DesignEquation(BaseModel):
    equation_id: str = Field(description="수식의 번호 또는 식별자 (예: Eq. 1, Implicit Eq. A)")
    latex_expression: str = Field(description="LaTeX 형식으로 표현된 핵심 설계 수식 (순수 수학 표기만)")
    target_parameter: str = Field(description="이 수식을 통해 최종적으로 sizing 또는 최적화하고자 하는 타겟 파라미터")
    variable_definitions: list[VariableDetail] = Field(description="수식에 사용된 주요 변수들의 정의 리스트")
    what_it_means_kr: list[str] = Field(description="이 수식이 회로 설계 관점에서 실제로 의미하는 물리학적/회로적 직관 리스트")
    why_we_need_it_kr: list[str] = Field(description="실적 설계/시뮬레이션 시 어떤 힌트를 주는지 핵심 리스트")
    connected_equations_or_dominant_variables: list[str] = Field(description="이 수식을 유도하기 위해 결합된 이전 수식 번호나 공정 특성을 타는 가장 지배적인 핵심 변수 기재")
    assumptions_and_conditions_kr: list[str] = Field(description="이 수식이 유효하기 위한 회로적 전제 조건 및 가정들을 한글로 정리")
    interview_defense_tip_kr: str = Field(description="실제 면접이나 디펜스 질문이 들어왔을 때 어떻게 답변하면 좋은지 치트키 가이드 제시")

class PerformanceSpec(BaseModel):
    metric_name: str = Field(description="성능 지표 명칭 (예: Technology, Supply Voltage, Power Consumption, Data Rate, Area, FoM)")
    metric_value: str = Field(description="해당 지표의 정량적 수치 및 단위")

class CircuitPaperAnalysis(BaseModel):
    paper_title: str = Field(description="논문 또는 문서의 제목")
    paper_summary_kr: str = Field(description="이 논문이 제안하는 회로 아키텍처/토폴로지의 핵심 요약 (4-5줄로 정밀 정리)")
    operating_principle_kr: list[str] = Field(description="핵심 블록별 회로 동작 원리 및 신호 흐름을 단계별 한글 리스트로 설명")
    performance_table: list[PerformanceSpec] = Field(description="주요 핵심 회로 성능 측정 지표 및 규격 리스트")
    core_equations: list[DesignEquation] = Field(description="논문에서 추출한 핵심 설계 수식 리스트")


# =====================================================================
# [Core Engine] PDF 텍스트 추출 및 LaTeX 가독성 확보용 후처리 필터링
# =====================================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text: 
            full_text += text + "\n"
    return full_text

def sanitize_latex(expr: str) -> str:
    """
    re.sub() 사용 시 백슬래시 이스케이프 버그 방지를 위해 chr(92)로 직접 우회 처리.
    LLM 결과물 중 깨진 수식 포맷 보정 및 회로 파라미터 렌더링 강제화 필터.
    """
    BS = chr(92) 
    def cmd(name): return BS + name
    def frac(num, den): return cmd("frac") + "{" + num + "}{" + den + "}"

    if not expr:
        return "N/A"
    cleaned = expr.strip().replace("#", "")

    if cleaned.startswith("$$") and cleaned.endswith("$$"):
        cleaned = cleaned[2:-2].strip()
    elif cleaned.startswith("$") and cleaned.endswith("$"):
        cleaned = cleaned[1:-1].strip()

    # 이미 명시적으로 기입된 명렁어가 포착되면 중복 적용 방지를 위해 바로 리턴
    if any(m in cleaned for m in [cmd("frac"), cmd("pi"), cmd("omega"),
                                   cmd("cdot"), cmd("alpha"), cmd("mu"),
                                   cmd("sqrt"), cmd("infty")]):
        return cleaned

    # 비교연산자 보호 처리를 위한 임시 토큰 파싱
    cleaned = (cleaned
               .replace(">=", "__GEQTOKEN__")
               .replace("<=", "__LEQTOKEN__")
               .replace("!=", "__NEQTOKEN__")
               .replace("->", "__RARROWTOKEN__"))

    # 자주 출몰하는 수식 특수문자 사전 맵핑
    greek_map = [
        (r"\b2pi\b",    "2" + cmd("pi")),
        (r"\bpi\b",     cmd("pi")),
        (r"\bomega\b",  cmd("omega")),
        (r"\bOmega\b",  cmd("Omega")),
        (r"\balpha\b",  cmd("alpha")),
        (r"\bbeta\b",   cmd("beta")),
        (r"\bgamma\b",  cmd("gamma")),
        (r"\bdelta\b",  cmd("delta")),
        (r"\bDelta\b",  cmd("Delta")),
        (r"\bmu\b",     cmd("mu")),
        (r"\bsigma\b",  cmd("sigma")),
        (r"\btau\b",    cmd("tau")),
        (r"\bphi\b",    cmd("phi")),
        (r"\btheta\b",  cmd("theta")),
        (r"\blambda\b", cmd("lambda")),
        (r"\binfty\b",  cmd("infty")),
        (r"\bsqrt\b",   cmd("sqrt")),
    ]
    for pattern, repl in greek_map:
        cleaned = re.sub(pattern, lambda m, r=repl: r, cleaned)

    # 괄호 Depth 체크를 통한 안전한 분수식 분할 분리 로직
    def split_fraction(s):
        depth = 0
        for i, c in enumerate(s):
            if c == "(": depth += 1
            elif c == ")": depth -= 1
            elif c == "/" and depth == 0:
                num = s[:i].strip()
                den = s[i+1:].strip()
                if num.startswith("(") and num.endswith(")"): num = num[1:-1].strip()
                if den.startswith("(") and den.endswith(")"): den = den[1:-1].strip()
                return num, den
        return None

    parts = cleaned.split("=")
    new_parts = []
    for part in parts:
        part = part.strip()
        result = split_fraction(part)
        if result:
            num, den = result
            part = frac(num, den)
        new_parts.append(part)
    cleaned = " = ".join(new_parts)

    cleaned = re.sub(r"\s*\*\s*", lambda m: " " + cmd("cdot") + " ", cleaned)

    # 현업/정형 논문 데이터 다빈도 등장 기생 성분 및 고정 변수 첨자 하드코딩 교정
    sub_map = [
        (r"\bIdrain\b", "I_{drain}"),
        (r"\bIbias\b",  "I_{bias}"),
        (r"\bVDD\b",    "V_{DD}"),
        (r"\bVGS\b",    "V_{GS}"),
        (r"\bVDS\b",    "V_{DS}"),
        (r"\bVth\b",    "V_{th}"),
        (r"\bVov\b",    "V_{ov}"),
        (r"\bRcasc\b",  "R_{casc}"),
        (r"\bRout\b",   "R_{out}"),
        (r"\bRMS\b",    "R_{MS}"),
        (r"\bCcasc\b",  "C_{casc}"),
        (r"\bCgs\b",    "C_{gs}"),
        (r"\bCgd\b",    "C_{gd}"),
        (r"\bCL\b",     "C_L"),
        (r"\bgm2\b",    "g_{m2}"),
        (r"\bgm\b",     "g_m"),
        (r"\bro\b",     "r_o"),
        (r"\bfo\b",     "f_0"),
        (r"\bTo\b",     "T_0"),
        (r"\bGBW\b",    cmd("mathrm") + "{GBW}"),
        (r"\bPM\b",     cmd("mathrm") + "{PM}"),
        (r"\bSNR\b",    cmd("mathrm") + "{SNR}"),
        (r"\bNF\b",     cmd("mathrm") + "{NF}"),
    ]
    for pattern, repl in sub_map:
        cleaned = re.sub(pattern, lambda m, r=repl: r, cleaned)

    cleaned = re.sub(
        r"([A-Za-z])([0-9]+)(?=[^a-zA-Z]|$)",
        lambda m: m.group(1) + "_{" + m.group(2) + "}",
        cleaned
    )

    cleaned = (cleaned
               .replace("__GEQTOKEN__",    " " + cmd("geq") + " ")
               .replace("__LEQTOKEN__",    " " + cmd("leq") + " ")
               .replace("__NEQTOKEN__",    " " + cmd("neq") + " ")
               .replace("__RARROWTOKEN__", " " + cmd("rightarrow") + " "))

    return re.sub(r"  +", " ", cleaned).strip()


# =====================================================================
# [Report Builder] 시각화 대시보드 및 다중 문서 결합 매트릭스 생성 모듈
# =====================================================================

def generate_html_dashboard(result_data: dict, output_path: str):
    operating_steps = "".join([f"<li>{step}</li>" for step in result_data.get('operating_principle_kr', [])])
    spec_rows = ""
    for spec in result_data.get('performance_table', []):
        spec_rows += f"""
        <tr>
            <td style="font-weight: bold; background-color: #f8fafc; color: #1e293b; width: 45%;">{spec.get('metric_name', '')}</td>
            <td style="color: #ea580c; font-weight: bold;">{spec.get('metric_value', '')}</td>
        </tr>"""

    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{result_data.get('paper_title', '논문 분석 결과')} - 분석 보고서</title>
        <script>
            window.MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']], processEscapes: true }} }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; color: #334155; margin: 40px; background-color: #f8fafc; line-height: 1.75; font-size: 16px; }}
            .header {{ background-color: #0f172a; color: white; padding: 35px; border-radius: 8px; border-bottom: 5px solid #38bdf8; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
            .header h2 {{ margin: 0 0 10px 0; font-size: 26px; }}
            .layout-container {{ display: flex; gap: 20px; margin-top: 25px; }}
            .left-block {{ flex: 1.8; }}
            .right-block {{ flex: 1.2; }}
            .summary-box {{ background-color: #f0f9ff; border: 1px solid #bae6fd; padding: 24px; border-radius: 10px; border-left: 6px solid #0284c7; height: calc(100% - 50px); }}
            .summary-box h4, .spec-box h4, .principle-box h4 {{ margin: 0 0 12px 0; color: #0369a1; font-size: 18px; font-weight: bold; }}
            .summary-box p {{ margin: 0; font-size: 15.5px; color: #1e293b; text-align: justify; line-height: 1.8; }}
            .spec-box {{ background-color: #fff7ed; border: 1px solid #ffedd5; padding: 24px; border-radius: 10px; border-left: 6px solid #f97316; }}
            .principle-box {{ background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 24px; border-radius: 10px; margin-top: 20px; border-left: 6px solid #475569; }}
            .principle-box li {{ font-size: 15.5px; color: #1e293b; margin-bottom: 8px; line-height: 1.8; }}
            .card {{ background-color: white; border: 1px solid #e2e8f0; padding: 35px; border-radius: 12px; margin-top: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.02); }}
            .card h3 {{ margin-top: 0; color: #1e293b; border-bottom: 2px solid #f1f5f9; padding-bottom: 12px; font-size: 20px; font-weight: bold; }}
            .math-box {{ 
                text-align: center; 
                background-color: #f8fafc; 
                padding: 30px; 
                font-size: 1.5vw; 
                min-font-size: 16px; 
                max-font-size: 26px; 
                border-radius: 8px; 
                margin: 20px 0; 
                color: #0f172a; 
                border: 1px solid #e2e8f0; 
                border-left: 6px solid #38bdf8; 
                word-break: break-word;
                overflow-wrap: break-word;
                white-space: normal;
                overflow-x: auto; 
            }}
            .math-box .MathJax {{ font-size: 100% !important; display: inline-block; max-width: 100%; }}
            .title {{ color: #0f172a; font-size: 17px; font-weight: bold; border-left: 5px solid #38bdf8; padding-left: 12px; margin-top: 30px; margin-bottom: 12px; }}
            .tip-box {{ background-color: #f0fdf4; border: 1px solid #dcfce7; color: #166534; padding: 22px; border-radius: 8px; margin-top: 20px; font-size: 15.5px; border-left: 6px solid #22c55e; line-height: 1.8; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 15px; }}
            th, td {{ border: 1px solid #e2e8f0; padding: 12px 16px; text-align: left; font-size: 15px; vertical-align: middle; }}
            th {{ background-color: #f8fafc; color: #475569; font-weight: bold; }}
            .card li {{ font-size: 15.5px; color: #334155; margin-bottom: 8px; line-height: 1.8; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>📄 Circuit Performance & Architecture Report (v2.6)</h2>
            <p><strong>Analyzed Document:</strong> {result_data.get('paper_title', 'N/A')}</p>
        </div>
        <div class="layout-container">
            <div class="left-block">
                <div class="summary-box">
                    <h4>💡 논문 아키텍처 핵심 요약 (Abstract Summary)</h4>
                    <p>{result_data.get('paper_summary_kr', '내용 없음')}</p>
                </div>
            </div>
            <div class="right-block">
                <div class="spec-box">
                    <h4>📊 핵심 성능 스펙 테이블 (Performance Specs)</h4>
                    <table>
                        <tbody>{spec_rows if spec_rows else "<tr><td colspan='2'>데이터가 없습니다.</td></tr>"}</tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="principle-box">
            <h4>⚙️ 상세 회로 동작 원리 블록 (Operating Principle)</h4>
            <ul>{operating_steps if operating_steps else "<li>동작 원리 데이터가 없습니다.</li>"}</ul>
        </div>
    """
    for eq in result_data.get('core_equations', []):
        pure_expression = sanitize_latex(eq.get('latex_expression', ''))
        html_template += f"""
        <div class="card">
            <h3>📊 공식 식별자: {eq.get('equation_id', 'N/A')} &nbsp;|&nbsp; 타겟 파라미터: <span style="color: #0284c7;">{eq.get('target_parameter', 'N/A')}</span></h3>
            <div class="math-box"> $${pure_expression}$$ </div>
            <div class="title">🔗 수식 유도 연결고리 및 기생 소자 성분 (Derivation Flow)</div>
            <ul>"""
        for flow in eq.get('connected_equations_or_dominant_variables', []): html_template += f"<li>{flow}</li>"
        html_template += f"""</ul>
            <div class="title">💡 회로적 직관과 물리적 의미 (What it means)</div>
            <ul>"""
        for item in eq.get('what_it_means_kr', []): html_template += f"<li>{item}</li>"
        html_template += f"""</ul>
            <div class="title">🎯 실전 설계 마진 & 트레이드오프 힌트 (Why we need it)</div>
            <ul>"""
        for item in eq.get('why_we_need_it_kr', []): html_template += f"<li>{item}</li>"
        html_template += f"""</ul>
            <div class="title">📋 공식 내부 수식 변수 기호 정의 (Variables)</div>
            <table>
                <thead><tr><th style="width:25%;">변수 기호</th><th>설계적 관점에서의 핵심 정의</th></tr></thead>
                <tbody>"""
        for var in eq.get('variable_definitions', []):
            v_name = sanitize_latex(var.get('variable_name', ''))
            html_template += f"<tr><td style='font-size: 16px; font-weight: bold; background-color: #f8fafc; color: #0f172a;'>\\({v_name}\\)</td><td style='font-size: 15px;'>{var.get('definition', '')}</td></tr>"
        html_template += f"""</tbody></table>
            <div class="title">🔑 수식 작동 전제 제약 조건 & 운영 영역 (Assumptions)</div>
            <ul>"""
        for asm in eq.get('assumptions_and_conditions_kr', []): html_template += f"<li>{asm}</li>"
        html_template += f"""</ul>
            <div class="tip-box">
                <strong>🔥 [치트키] 면접 및 피어 리뷰 심사 대비 심층 디펜스 가이드:</strong><br>
                <p style="margin: 8px 0 0 0;">{eq.get('interview_defense_tip_kr', '내용 없음')}</p>
            </div>
        </div>"""
    html_template += "</body></html>"
    with open(output_path, "w", encoding="utf-8") as f: f.write(html_template)

def generate_integrated_matrix(all_results: list, output_path: str):
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>회로 설계 선행 연구 선행 연구 통합 비교 분석표</title>
        <script>
            window.MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']], processEscapes: true }} }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; color: #334155; margin: 40px; background-color: #f1f5f9; font-size: 15px; }}
            .header {{ background-color: #1e293b; color: white; padding: 35px; border-radius: 12px; border-bottom: 5px solid #38bdf8; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
            .header h1 {{ margin: 0 0 5px 0; font-size: 28px; }}
            table {{ width: 100%; border-collapse: collapse; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
            th, td {{ padding: 16px 20px; text-align: left; font-size: 14.5px; vertical-align: top; border-bottom: 1px solid #f1f5f9; line-height: 1.6; }}
            th {{ background-color: #0f172a; color: white; font-size: 15.5px; font-weight: bold; }}
            tr:hover {{ background-color: #f8fafc; }}
            .paper-column {{ width: 18%; font-weight: bold; color: #1e293b; }}
            .summary-column {{ width: 24%; color: #334155; text-align: justify; }}
            .spec-column {{ width: 18%; border-left: 1px solid #f1f5f9; }}
            .spec-sub-table {{ width: 100%; margin: 0; }}
            .spec-sub-table td {{ padding: 5px 6px; font-size: 13px; border: none; border-bottom: 1px dashed #e2e8f0; }}
            .eq-box {{ background-color: #f8fafc; padding: 14px; border-radius: 6px; border: 1px solid #e2e8f0; margin-top: 8px; font-size: 16px; text-align: center; overflow-x: auto; }}
            .bullet-list {{ margin: 0; padding-left: 18px; }}
            .bullet-list li {{ margin-bottom: 6px; color: #475569; }}
            .bold-target {{ font-weight: bold; color: #0284c7; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 회로 설계 선행 연구 선행 연구 통합 비교 분석표</h1>
            <p>선행 연구 논문들의 토폴로지 아키텍처 및 정량적 스펙 규격 분석 리포트</p>
        </div>
        <table>
            <thead>
                <tr>
                    <th>분석 대상 논문 제목 (Paper Title)</th>
                    <th>💡 아키텍처 요약 (Summary)</th>
                    <th>📈 성능 요약 스펙</th>
                    <th>대표 핵심 수식 (Core Equation)</th>
                    <th>핵심 설계 가정 및 제약 조건</th>
                </tr>
            </thead>
            <tbody>
    """
    for data in all_results:
        paper_title = data.get('paper_title', 'N/A')
        paper_sum = data.get('paper_summary_kr', '내용 요약 정보가 없습니다.')
        matrix_spec_rows = ""
        for spec in data.get('performance_table', []):
            matrix_spec_rows += f"<tr><td style='font-weight:500; color:#475569;'>{spec.get('metric_name','')}:</td><td style='color:#ea580c; font-weight:bold;'>{spec.get('metric_value','')}</td></tr>"
        matrix_spec_table = f"<table class='spec-sub-table'><tbody>{matrix_spec_rows}</tbody></table>" if matrix_spec_rows else "스펙 없음"

        if data.get('core_equations'):
            top_eq = data['core_equations'][0]
            target_param = top_eq.get('target_parameter', 'N/A')
            pure_matrix_eq = sanitize_latex(top_eq.get('latex_expression', ''))
            asm_list = "".join([f"<li>{a}</li>" for a in top_eq.get('assumptions_and_conditions_kr', [])])
        else:
            target_param = "N/A"; pure_matrix_eq = "N/A"; asm_list = "<li>조건 없음</li>"

        html_template += f"""
                <tr>
                    <td class="paper-column">{paper_title}</td>
                    <td class="summary-column">{paper_sum}</td>
                    <td class="spec-column">{matrix_spec_table}</td>
                    <td style="width: 24%;"><span class="bold-target">🎯 타겟 파라미터: {target_param}</span><div class="eq-box">$${pure_matrix_eq}$$</div></td>
                    <td style="width: 16%; border-left: 1px solid #f1f5f9;"><ul class="bullet-list">{asm_list}</ul></td>
                </tr>"""
    html_template += "</tbody></table></body></html>"
    with open(output_path, "w", encoding="utf-8") as f: f.write(html_template)


# =====================================================================
# [User Interface] Tkinter 기반 조작용 GUI 창 클래스
# =====================================================================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Analog/RF Circuit Paper Analyzer v2.7_By_SH")
        self.root.geometry("1030x700")
        
        # 파일 캐싱 및 중단 제어 플래그
        self.history_file = "key_history.json"
        self.is_running = False
        self.stop_requested = False
        
        self.dot_count = 0
        self.current_raw_filename = ""
        self.status_phase = "ready"
        
        # 기본 프로그레스바 테마 셋업
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Custom.Horizontal.TProgressbar", 
                        troughcolor='#f1f5f9', background='#107c41', 
                        thickness=22, bordercolor='#cbd5e1')
        
        main_paned = tk.PanedWindow(root, orient="horizontal")
        main_paned.pack(fill="both", expand=True)
        
        left_pane = tk.Frame(main_paned, padx=10, pady=10)
        right_pane = tk.LabelFrame(main_paned, text=" 📂 분석 완료된 개별 리포트 목록 (더블클릭 시 즉시 열기) ", font=("맑은 고딕", 10, "bold"), padx=10, pady=10)
        
        main_paned.add(left_pane, width=580)
        main_paned.add(right_pane, width=450)
        
        # -------------------------------------------------------------
        # Left Panel Component Components
        # -------------------------------------------------------------
        key_group = tk.LabelFrame(left_pane, text=" 🔑 Gemini API 설정 ", font=("맑은 고딕", 10, "bold"), padx=12, pady=8, fg="#0284c7")
        key_group.pack(fill="x", pady=(0, 10))
        
        url_label = tk.Label(key_group, text="🔗 여기를 클릭하여 구글 API 키를 확인/발급받으세요", font=("맑은 고딕", 9, "underline"), fg="#0066cc", cursor="hand2")
        url_label.pack(anchor="w", pady=(0, 6))
        url_label.bind("<Button-1>", lambda e: webbrowser.open("https://aistudio.google.com/api-keys"))
        
        input_container = tk.Frame(key_group)
        input_container.pack(fill="x")
        tk.Label(input_container, text="API KEY 입력:", font=("맑은 고딕", 9, "bold")).pack(side="left")
        
        self.ent_key = tk.Entry(input_container, font=("Consolas", 10), fg="#0f172a")
        self.ent_key.pack(side="left", fill="x", expand=True, padx=(10, 5))
        
        # 키 히스토리 복원 및 선택 바인딩
        self.history_keys = self.load_key_history()
        self.opt_var = tk.StringVar(root)
        if self.history_keys:
            self.opt_var.set("📜 최근 사용한 API 키 기록 선택")
            self.ent_key.insert(0, self.history_keys[0])
        else:
            self.opt_var.set("📜 저장된 API 키 기록 없음")
            self.ent_key.insert(0, "AIzaSy...")

        self.menu_history = tk.OptionMenu(key_group, self.opt_var, *(self.history_keys if self.history_keys else ["기록 없음"]), command=self.on_history_select)
        self.menu_history.config(font=("맑은 고딕", 9), relief="groove")
        self.menu_history.pack(fill="x", pady=(6, 0))
        
        folder_group = tk.Frame(left_pane, pady=5)
        folder_group.pack(fill="x")
        tk.Label(folder_group, text="논문 폴더:", font=("맑은 고딕", 10, "bold")).pack(side="left")
        
        self.ent_folder = tk.Entry(folder_group, font=("맑은 고딕", 10))
        self.ent_folder.pack(side="left", fill="x", expand=True, padx=10)
        
        tk.Button(folder_group, text="폴더 선택", command=self.browse_folder, bg="#e1e1e1", padx=10).pack(side="right")
        
        tk.Label(left_pane, text="⚠️  주의: 선택할 폴더 내부에 반드시 분석하고자 하는 'PDF 파일만' 모아서 넣어주세요.", font=("맑은 고딕", 9, "bold"), fg="#b91c1c").pack(anchor="w", pady=(2, 8))
        
        control_group = tk.Frame(left_pane, pady=5)
        control_group.pack(fill="x")
        
        self.btn_start = tk.Button(control_group, text="⚡ 요약 시작", font=("맑은 고딕", 10, "bold"), bg="#107c41", fg="white", pady=6, command=self.start_analysis_thread)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 3))
        
        self.btn_stop = tk.Button(control_group, text="🛑 요약 중단", font=("맑은 고딕", 10, "bold"), bg="#b91c1c", fg="white", pady=6, state="disabled", command=self.request_stop_analysis)
        self.btn_stop.pack(side="left", fill="x", expand=True, padx=(3, 3))
        
        self.btn_open_result = tk.Button(control_group, text="📊 논문별 비교 분석표", font=("맑은 고딕", 10, "bold"), bg="#0078d4", fg="white", pady=6, state="disabled", command=self.open_result_page)
        self.btn_open_result.pack(side="left", fill="x", expand=True, padx=(3, 0))
        
        tk.Label(left_pane, text="실행 로그:", font=("맑은 고딕", 10, "bold")).pack(anchor="w", pady=(5, 2))
        
        self.txt_log = scrolledtext.ScrolledText(left_pane, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", height=11)
        self.txt_log.pack(fill="both", expand=True, pady=(0, 5))
        
        self.frame_progress = tk.LabelFrame(left_pane, text=" 📊 LOADING ", font=("맑은 고딕", 10, "bold"), fg="#334155", padx=12, pady=10)
        self.frame_progress.pack(fill="x", side="bottom", pady=(5, 0))
        
        self.lbl_progress_status = tk.Label(self.frame_progress, text="대기 중 (분석이 시작되면 활성화됩니다)", font=("맑은 고딕", 9), fg="#64748b")
        self.lbl_progress_status.pack(anchor="w", fill="x", expand=True)
        
        self.pbar = ttk.Progressbar(self.frame_progress, orient="horizontal", mode="determinate", style="Custom.Horizontal.TProgressbar")
        self.pbar.pack(fill="x", pady=(8, 5))
        
        self.lbl_progress_percent = tk.Label(self.frame_progress, text="0% (0 / 0 편)", font=("맑은 고딕", 9, "bold"), fg="#475569")
        self.lbl_progress_percent.pack(anchor="e")

        # -------------------------------------------------------------
        # Right Panel Component Components
        # -------------------------------------------------------------
        list_scroll = tk.Scrollbar(right_pane, orient="vertical")
        list_scroll.pack(side="right", fill="y")
 
        self.list_reports = tk.Listbox(right_pane, font=("맑은 고딕", 10), yscrollcommand=list_scroll.set, selectmode="single", highlightthickness=1)
        self.list_reports.pack(fill="both", expand=True, pady=(0, 10))
        list_scroll.config(command=self.list_reports.yview)

        right_btn_group = tk.Frame(right_pane)
        right_btn_group.pack(fill="x")
        
        tk.Button(right_btn_group, text="🔄 목록 새로고침", font=("맑은 고딕", 10), bg="#f1f5f9", fg="#334155", relief="groove", pady=6, 
                  command=lambda: threading.Thread(target=self.refresh_report_list, daemon=True).start()).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        tk.Button(right_btn_group, text="🔍 선택한 리포트 웹뷰로 열기", font=("맑은 고딕", 10, "bold"), bg="#e2e8f0", fg="#0f172a", relief="groove", pady=6, 
                  command=self.open_selected_report).pack(side="left", fill="x", expand=True)
        
        self.list_reports.bind("<Double-Button-1>", lambda event: self.open_selected_report())
 

    def shorten_filename(self, filename, max_len=45):
        if len(filename) <= max_len: 
            return filename
        return filename[:15] + " ... " + filename[-25:]

    def animate_progress(self):
        """ 프로그레스 바 텍스트에 동적인 점 애니메이션 효과를 주는 스레드 전용 루프 """
        if not self.is_running or self.stop_requested: 
            return
        
        self.dot_count = (self.dot_count % 3) + 1
        dots = "." * self.dot_count
        short_name = self.shorten_filename(self.current_raw_filename)
        
        if self.status_phase == "extract":
            self.lbl_progress_status.config(text=f"⏳ [{short_name}] 텍스트 스캔 및 추출 중{dots}", fg="#ea580c")
        elif self.status_phase == "ai":
            self.lbl_progress_status.config(text=f"🤖 분석 중: {short_name}{dots}", fg="#107c41")
            
        self.root.after(400, self.animate_progress)

    def update_progress_metrics(self, current_index, current_file_name, total_count):
        self.pbar["maximum"] = total_count
        self.pbar["value"] = current_index
        self.current_raw_filename = current_file_name
        percent = int((current_index / total_count) * 100) if total_count > 0 else 0
        self.lbl_progress_percent.config(text=f"{percent}% ({current_index} / {total_count} 편)", fg="#107c41")

    def reset_progress_ui(self, status_text="대기 중 (연산 프로세스 종료)"):
        self.pbar["value"] = 0
        self.status_phase = "ready"
        self.lbl_progress_status.config(text=status_text, fg="#64748b")
        self.lbl_progress_percent.config(text="0%", fg="#475569")

    def load_key_history(self):
        if not os.path.exists(self.history_file): 
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                encoded_list = json.load(f)
                return [base64.b64decode(k.encode()).decode() for k in encoded_list]
        except Exception: 
            return []

    def save_key_history(self, new_key):
        if not new_key or len(new_key) < 15 or "클릭" in new_key or "AIzaSy" in new_key: 
            return
        keys = self.load_key_history()
        if new_key in keys: 
            keys.remove(new_key)
        keys.insert(0, new_key)
        keys = keys[:5]
        try:
            encoded_list = [base64.b64encode(k.encode()).decode() for k in keys]
            with open(self.history_file, "w", encoding="utf-8") as f: 
                json.dump(encoded_list, f)
        except Exception: 
            pass

    def on_history_select(self, selected_key):
        if selected_key and "기록" not in selected_key:
            self.ent_key.delete(0, tk.END)
            self.ent_key.insert(0, selected_key)
            self.opt_var.set("📜 최근 사용한 API 키 기록 선택")

    def log(self, text):
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.ent_folder.delete(0, tk.END)
            self.ent_folder.insert(0, folder_selected)
            threading.Thread(target=self.refresh_report_list, daemon=True).start()

    def refresh_report_list(self):
        self.root.after(0, lambda: self.list_reports.delete(0, tk.END))
        target_dir = self.ent_folder.get().strip()
        if not target_dir or not os.path.exists(target_dir): 
            return
            
        files = os.listdir(target_dir)
        html_reports = [f for f in files if f.lower().endswith("_dashboard.html") and not f.startswith("__통합")]
        
        if html_reports:
            for report in sorted(html_reports):
                clean_name = report.replace("_dashboard.html", "")
                self.root.after(0, lambda name=clean_name: self.list_reports.insert(tk.END, f"📄 {name}"))
        else:
            self.root.after(0, lambda: self.list_reports.insert(tk.END, "📭 분석 완료된 개별 리포트가 없습니다."))
            
        if os.path.exists(os.path.join(target_dir, "__통합_비교_분석표_대시보드.html")):
            self.root.after(0, lambda: self.btn_open_result.config(state="normal"))

    def open_selected_report(self):
        selection = self.list_reports.curselection()
        if not selection: 
            return
        selected_text = self.list_reports.get(selection[0])
        if "분석 완료된" in selected_text or "📭" in selected_text: 
            return
        full_html_path = os.path.join(self.ent_folder.get().strip(), selected_text.replace("📄 ", "") + "_dashboard.html")
        if os.path.exists(full_html_path): 
            webbrowser.open(full_html_path)

    def open_result_page(self):
        matrix_path = os.path.join(self.ent_folder.get().strip(), "__통합_비교_분석표_대시보드.html")
        if os.path.exists(matrix_path): 
            webbrowser.open(matrix_path)

    def start_analysis_thread(self):
        current_key = self.ent_key.get().strip()
        if not current_key or "AIzaSy..." in current_key or len(current_key) < 15:
            messagebox.showwarning("경고", "유효한 Gemini API Key를 정확히 입력해 주세요.")
            return
        if not self.ent_folder.get().strip():
            messagebox.showwarning("경고", "논문 폴더를 먼저 선택해 주세요.")
            return
            
        self.save_key_history(current_key)
        
        self.is_running = True
        self.stop_requested = False
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_open_result.config(state="disabled")
        
        threading.Thread(target=self.run_analysis, args=(current_key,), daemon=True).start()
        
        self.status_phase = "extract"
        self.dot_count = 0
        self.root.after(100, self.animate_progress)

    def request_stop_analysis(self):
        if self.is_running:
            self.stop_requested = True
            self.log("\n🛑 [중단 요청] 현재 연산 중인 논문까지만 마감하고 상태를 업데이트합니다...")
            self.btn_stop.config(state="disabled")

    def run_analysis(self, api_key):
        target_dir = self.ent_folder.get().strip()
        if not os.path.exists(target_dir):
            self.log(f"❌ 오류: '{target_dir}' 경로를 찾을 수 없습니다.")
            self.reset_ui_buttons()
            return
        
        pdf_files = [f for f in os.listdir(target_dir) if f.lower().endswith(".pdf")]
        if not pdf_files:
            self.log("📭 폴더 안에 분석 가능한 PDF 파일이 없습니다.")
            self.reset_ui_buttons()
            return
        
        total_count = len(pdf_files)
        self.log(f"📚 총 {total_count}개의 논문 PDF 스캔 및 동기화 무결성 점검을 개시합니다.")
        
        client = None
        try: 
            client = genai.Client(api_key=api_key)
        except Exception:
            self.log(f"❌ 초기화 실패: 구글 API 인증 에러.")
            self.reset_ui_buttons()
            return

        all_parsed_results = []
        
        for idx, pdf_file in enumerate(pdf_files, 1):
            if self.stop_requested: 
                break
            
            self.root.after(0, lambda i=idx, f=pdf_file: self.update_progress_metrics(i, f, total_count))
            
            pdf_path           = os.path.join(target_dir, pdf_file)
            expected_json_name = os.path.join(target_dir, pdf_file.replace(".pdf", "_analysis.json"))
            expected_html_name = os.path.join(target_dir, pdf_file.replace(".pdf", "_dashboard.html"))
            
            # 로컬 캐시 검증 디바이스 체크 (동일 파일 중복 연산 차단)
            if os.path.exists(expected_json_name) and os.path.exists(expected_html_name):
                try:
                    with open(expected_json_name, "r", encoding="utf-8") as f:
                        cached_data = json.load(f)
                    _equations = cached_data.get('core_equations', [])
                    _eq_valid = not _equations or len(_equations[0].get('what_it_means_kr', [])) >= 1
                    if 'operating_principle_kr' in cached_data and _eq_valid:
                        self.log(f"⏭️  [Skip] 동기화 완료되어 고속 패스: '{pdf_file}'")
                        all_parsed_results.append(cached_data)
                        continue
                except Exception:
                    pass

            try:
                self.status_phase = "extract"
                self.log(f"⏳ [{pdf_file}] 대용량 텍스트 파싱 및 물리 버퍼 스캔 시작...")
                self.root.update()
                
                paper_text = extract_text_from_pdf(pdf_path)
                if not paper_text.strip():
                    self.log(f"⚠️ [{pdf_file}] 추출된 텍스트가 없습니다. 스캔된 이미지 PDF일 수 있습니다.")
                    continue
                    
                self.log(f"📝 [{pdf_file}] 텍스트 스캔 완료 (총 {len(paper_text)}자 확보). 대시보드 구조화 작업을 위해 AI 서버로 전송합니다.")
                
                self.status_phase = "ai"
                self.log(f"🤖 [{pdf_file}] Gemini AI 아키텍처 및 스펙 분석 반영 중...")
                
                # 프롬프트 인스트럭션 자연어 튜닝 수행
                prompt = f"""
                You are a world-class senior IC designer in Analog/RF circuits.
                Analyze the academic paper provided below and extract the core circuit architecture, quantitative performance table, and critical design equations.
                
                Guidelines for response compliance:
                1. 'paper_summary_kr': Provide a deeply comprehensive Korean summary (4-5 sentences) covering the circuit topology, architecture, and performance goals.
                2. 'operating_principle_kr': Provide detailed step-by-step Korean bullet points explaining block-level circuit operations and signal/charge flows meticulously.
                3. 'performance_table': Extract core implementation specs or measurement metrics (e.g., Technology, Supply Voltage, Power, Area).
                4. 'core_equations': 
                   - If the paper does not contain explicit equations, treat key sub-blocks, schemes, or major design trade-offs as pseudo-equations.
                   - For 'equation_id', write the clear sub-block or scheme name.
                   - For 'latex_expression', generate a clean standard qualitative expression WITHOUT any dollar signs ($) or markdown wrappers. Example: "Gain \\propto g_m \\cdot R_{{out}}" or "I_{{out}} = V_{{in}} / R".
                   - For 'what_it_means_kr' and 'why_we_need_it_kr', provide detailed analytical Korean descriptions as a list of strings.
                
                Document Content:
                ---
                {paper_text}
                ---
                """
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config={'response_mime_type': 'application/json', 'response_schema': CircuitPaperAnalysis, 'temperature': 0.1}
                )
                
                result_data = json.loads(response.text)
                all_parsed_results.append(result_data)
                
                with open(expected_json_name, "w", encoding="utf-8") as f: 
                    f.write(response.text)
                generate_html_dashboard(result_data, expected_html_name)
                self.log(f"✅ [{pdf_file}] 개별 고품질 대시보드 리포트 추출 완료.")
                
                self.root.after(0, self.refresh_report_list)
                
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    self.log(f"\n🚫 [일일 한도 도달] 할당량 한계로 중단되었습니다.")
                    break
                elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                    self.log(f"\n⚠️ [서버 트래픽 과부하] 잠시 후 이어서 시도해 주세요.\n")
                    break
                else:
                    self.log(f"❌ [{pdf_file}] 파싱 누락 오류 패스. (세부 원인: {err_msg[:80]})")

        if self.stop_requested:
            self.root.after(0, lambda: self.reset_progress_ui("🛑 중단됨 (이전 연산 백업 완료)"))
        else:
            self.root.after(0, lambda: self.reset_progress_ui("✅ 완료 (폴더 내 모든 선행 연구 동기화 성공)"))

        if all_parsed_results:
            matrix_name = os.path.join(target_dir, "__통합_비교_분석표_대시보드.html")
            generate_integrated_matrix(all_parsed_results, matrix_name)
            self.log(f"\n🏆 [대시보드 빌드] 선행 연구 비교 분석표 갱신 완료!")
            self.root.after(0, lambda: self.btn_open_result.config(state="normal"))
            self.root.after(0, self.refresh_report_list)
        
        self.reset_ui_buttons()

    def reset_ui_buttons(self):
        self.is_running = False
        self.stop_requested = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_stop.config(state="disabled"))


if __name__ == "__main__":
    main_window = tk.Tk()
    app = App(main_window)
    main_window.mainloop()
