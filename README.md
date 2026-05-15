# VIC — Visualization Integrity Checklist

> A semi-automated Python framework for detecting misleading data visualizations in digital media.

---

## What is VIC?

Most data visualization frameworks tell **designers** how to make better charts. VIC is built for **readers** — it lets you audit any existing chart and score it for misleading elements, without needing access to the underlying data.

VIC evaluates charts across **4 dimensions** and **12 criteria**, producing a **Misleading Risk Score (MRS)** from 0–100.

| MRS Range | Risk Band |
|-----------|-----------|
| 0 – 30    | 🟢 Low     |
| 31 – 60   | 🟡 Medium  |
| 61 – 100  | 🔴 High    |

---

## Why VIC?

Existing frameworks (Tufte, Few, Cairo) have three major gaps:

- ❌ All three are **designer-facing** — they assume you built the chart
- ❌ None address **digital media context** where misleading charts spread
- ❌ None produce a **quantitative score** to compare charts systematically

VIC fills all three gaps.

---

## The 4 Dimensions

| Dimension | Criteria | Max Score |
|---|---|---|
| **Axis Integrity** | Y-axis at zero, consistent scale, axis labels | 25 pts |
| **Visual Honesty** | No 3D chart, safe colors, chart type fits data | 25 pts |
| **Contextual Completeness** | Source cited, timeframe shown, sample size stated | 25 pts |
| **Audience Clarity** | Descriptive title, legend present, readable | 25 pts |

---

## The 12 Criteria

| ID  | Criterion | Method | Penalty |
|-----|-----------|--------|---------|
| AX1 | Y-axis starts at zero | Auto | 8 pts |
| AX2 | Consistent axis scale | Auto | 9 pts |
| AX3 | Axis labels present | Semi | 8 pts |
| VH1 | No 3D chart used | Auto | 9 pts |
| VH2 | Colors not misleading | Auto | 8 pts |
| VH3 | Chart type suits data | Manual | 8 pts |
| CC1 | Data source cited | Semi | 9 pts |
| CC2 | Timeframe visible | Semi | 8 pts |
| CC3 | Sample size mentioned | Manual | 8 pts |
| AC1 | Descriptive title present | Semi | 9 pts |
| AC2 | Legend present (if multi-series) | Auto | 8 pts |
| AC3 | Readable without expertise | Manual | 8 pts |

**Method types:**
- `Auto` — Python detects automatically
- `Semi` — keyword scan on chart text
- `Manual` — pre-loaded from `manual_answers.json`

---

## Project Structure

```
vic-framework/
│
├── vic_framework.py        # Core VIC scoring engine
├── manual_answers.json     # Pre-loaded manual answers for batch mode
├── run_vic.py              # Batch runner script
│
├── charts/                 # Chart images used in evaluation
│   ├── chart01.png
│   ├── chart02.png
│   └── ... (12 total)
│
├── results/
│   └── vic_results.csv     # Scored output for all 12 charts
│
└── paper/
    └── VIC_IEEE_Paper.docx # Full IEEE research paper
```

---

## Installation

```bash
git clone https://github.com/yourusername/vic-framework.git
cd vic-framework
pip install matplotlib Pillow numpy
```

No other dependencies required.

---

## Usage

### Score a single image (PNG/JPG screenshot)

```python
from vic_framework import vic_score_image

result = vic_score_image("chart01.png")
result.print_report()
```

### Score a Matplotlib chart directly

```python
import matplotlib.pyplot as plt
from vic_framework import vic_score_matplotlib

fig, ax = plt.subplots()
ax.bar(["A", "B", "C"], [10, 20, 30])
ax.set_title("My Chart")
ax.set_xlabel("Category")
ax.set_ylabel("Value")

result = vic_score_matplotlib(fig, ax, chart_name="My Chart")
result.print_report()
```

### Batch score multiple charts (fully automated)

```bash
python run_vic.py
```

This reads `manual_answers.json` automatically — no prompts needed — and saves everything to `vic_results.csv`.

## Results: 12-Chart Evaluation

| Chart | Description | MRS | Risk |
|-------|-------------|-----|------|
| 01 | Reuters — FL Gun Deaths (Inverted Y-axis) | 33 | 🟡 Medium |
| 02 | Fox News — Obama Unemployment (Truncated) | 24 | 🟢 Low |
| 03 | Obama Unemployment Area Chart | 24 | 🟢 Low |
| 04 | PS3 vs Xbox 360 Pictograph | 58 | 🟡 Medium |
| 05 | U.S. Unemployment Flipped Y-axis | 33 | 🟡 Medium |
| 06 | Fox News 3D Pie Chart (sums to 193%) | 41 | 🟡 Medium |
| 07 | Sports Ticket Price Pictograph | **66** | 🔴 **High** |
| 08 | Kansas COVID Dual-Axis Chart | 33 | 🟡 Medium |
| 09 | COVID Active Cases Line Chart | 8 | 🟢 Low |
| 10 | College Tuition vs Earnings | 33 | 🟡 Medium |
| 11 | Global Temperature Flat Line | 25 | 🟢 Low |
| 12 | Germany COVID Choropleth Maps | 33 | 🟡 Medium |
| **Avg** | | **34.2** | 🟡 **Medium** |

**Key findings:**
- 🔴 **67%** of charts scored medium-to-high risk
- 📉 **Contextual Completeness** was the most violated dimension (avg 10/25)
- 📊 **100% of charts** failed CC3 — no chart stated its sample size
- ✅ **Visual Honesty** was strongest (avg 21/25)

---

## Research Paper

This framework is documented in a full IEEE-format research paper:

**"VIC: A Semi-Automated Visualization Integrity Checklist Framework for Detecting Misleading Data Visualizations in Digital Media"**

The paper covers:
- Literature review (Tufte, Few, Cairo — and their gaps)
- Full VIC framework design and justification
- Methodology and evaluation procedure
- Results and discussion

📄 Available in `/paper/VIC_IEEE_Paper.docx`

---

## Limitations

- Image-based checks use heuristics — may produce false positives on unusual chart layouts
- Manual criteria (VH3, CC3, AC3) introduce subjectivity when applied by human evaluators
- Evaluated on 12 charts — larger-scale validation is needed
- AX2 (scale consistency) and VH1 (3D detection) currently skipped for image inputs

---

## Future Work

- [ ] OCR integration (`pytesseract`) to automate CC3 and AC3
- [ ] Web-based UI for non-technical users (journalists, educators)
- [ ] Larger validation dataset (100+ charts)
- [ ] Inter-rater reliability study for manual criteria
- [ ] ML-based chart type detection for VH3 automation

---

## References

- Tufte, E. R. (2001). *The Visual Display of Quantitative Information*. Graphics Press.
- Few, S. (2012). *Show Me the Numbers*. Analytics Press.
- Cairo, A. (2016). *The Truthful Art*. New Riders.
- Hullman, J. & Diakopoulos, N. (2011). Visualization rhetoric. *IEEE TVCG*, 17(12).
- Pandey, A. et al. (2014). The persuasive power of data visualization. *IEEE TVCG*, 20(12).

---

*Built as part of a data science research project on visualization integrity and media misinformation.*
