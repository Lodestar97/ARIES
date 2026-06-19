# ARIES
AI-powered Paper Analysis Tool for Analog/RF IC Designers

## Overview

ARIES는 Analog/RF 회로 설계자가 논문을 읽을 때 반복적으로 수행하는 작업을 줄이기 위해 만든 도구입니다.

PDF 논문으로부터

- 핵심 수식
- 변수 정의
- 성립 조건
- 회로적 의미
- 성능 지표

등을 자동으로 추출하고 HTML 대시보드 형태로 정리합니다.

---

## Motivation

연구실에서 프로젝트를 진행하면서 여러 논문을 비교해야 했습니다.

비슷한 수식이라도 적용 조건과 가정이 조금씩 달라 이를 직접 정리하는 데 많은 시간이 필요했습니다.

ARIES는 이러한 과정을 효율화하기 위해 개발되었습니다.

---

## Features

- PDF batch processing
- Equation extraction
- Variable definition analysis
- Assumption extraction
- HTML dashboard generation
- Cache support

---

## Example

Input

```
paper.pdf
```

Output

```
paper_summary.html
```

---

## Tech Stack

- Python
- OpenAI API
- PyMuPDF
- Markdown
- HTML

---

## Future Work

- Performance table extraction
- Equation dependency graph
- Multi-paper comparison
