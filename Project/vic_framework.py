"""
=============================================================
  VIC — Visualization Integrity Checklist
  A Semi-Automated Framework for Detecting Misleading Charts
  Research Paper Tool · Data Science
=============================================================

USAGE:
  # For a Matplotlib figure:
      fig, ax = plt.subplots()
      ax.bar(...)
      result = vic_score_matplotlib(fig, ax)

  # For an image file (PNG/JPG):
      result = vic_score_image("path/to/chart.png")

  # Both return a VICResult with MRS score + full report
=============================================================
"""

import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Optional

# ── optional imports (graceful fallback) ──────────────────────
try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ─────────────────────────────────────────────────────────────
#  DATA STRUCTURES
# ─────────────────────────────────────────────────────────────

@dataclass
class CriterionResult:
    id: str
    dimension: str
    name: str
    passed: bool           # True = chart is honest on this criterion
    penalty: int           # Points added to MRS if failed
    points_lost: int       # 0 if passed, else penalty
    method: str            # "auto" | "semi" | "manual"
    note: str = ""


@dataclass
class VICResult:
    chart_name: str
    chart_type: str        # "matplotlib" | "image"
    criteria: list = field(default_factory=list)
    mrs: int = 0           # Misleading Risk Score  0–100
    risk_band: str = ""    # Low / Medium / High
    dimension_scores: dict = field(default_factory=dict)

    def print_report(self):
        _print_report(self)


# ─────────────────────────────────────────────────────────────
#  SCORING CONSTANTS
# ─────────────────────────────────────────────────────────────

DIMENSIONS = {
    "axis":    ("Axis Integrity",          25),
    "visual":  ("Visual Honesty",          25),
    "context": ("Contextual Completeness", 25),
    "clarity": ("Audience Clarity",        25),
}

CRITERIA_META = [
    # (id,              dimension,  name,                           penalty, method)
    ("AX1", "axis",    "Y-axis starts at zero",                    8,  "auto"),
    ("AX2", "axis",    "Consistent axis scale",                    9,  "auto"),
    ("AX3", "axis",    "Axis labels present",                      8,  "semi"),
    ("VH1", "visual",  "No 3D chart used",                         9,  "auto"),
    ("VH2", "visual",  "Colors are not misleading",                8,  "auto"),
    ("VH3", "visual",  "Chart type suits the data",                8,  "manual"),
    ("CC1", "context", "Data source is cited",                     9,  "semi"),
    ("CC2", "context", "Timeframe is visible",                     8,  "semi"),
    ("CC3", "context", "Sample size mentioned",                    8,  "manual"),
    ("AC1", "clarity", "Title is present and descriptive",         9,  "semi"),
    ("AC2", "clarity", "Legend present (if multi-series)",         8,  "auto"),
    ("AC3", "clarity", "Readable without domain expertise",        8,  "manual"),
]


# ─────────────────────────────────────────────────────────────
#  MATPLOTLIB CHECKS
# ─────────────────────────────────────────────────────────────

def _mpl_check_yaxis_zero(ax) -> tuple[bool, str]:
    """AX1 — Y-axis should start at or very near zero."""
    try:
        ymin, _ = ax.get_ylim()
        if ymin <= 0.01:
            return True, f"Y-axis starts at {ymin:.2f} (OK)"
        return False, f"Y-axis starts at {ymin:.2f} — truncated axis detected"
    except Exception as e:
        return True, f"Could not determine y-limits: {e}"


def _mpl_check_scale_consistency(ax) -> tuple[bool, str]:
    """AX2 — Tick intervals should be uniform (no broken axes)."""
    try:
        ticks = ax.get_yticks()
        if len(ticks) < 2:
            return True, "Too few ticks to evaluate scale"
        gaps = [round(ticks[i+1] - ticks[i], 6) for i in range(len(ticks)-1)]
        unique_gaps = set(gaps)
        if len(unique_gaps) == 1:
            return True, f"Uniform tick spacing: {gaps[0]}"
        return False, f"Non-uniform tick spacing detected: {unique_gaps}"
    except Exception as e:
        return True, f"Scale check skipped: {e}"


def _mpl_check_axis_labels(ax) -> tuple[bool, str]:
    """AX3 — Both X and Y axes should have labels."""
    xlabel = ax.get_xlabel().strip()
    ylabel = ax.get_ylabel().strip()
    if xlabel and ylabel:
        return True, f"X='{xlabel}', Y='{ylabel}'"
    missing = []
    if not xlabel:
        missing.append("X-axis label")
    if not ylabel:
        missing.append("Y-axis label")
    return False, f"Missing: {', '.join(missing)}"


def _mpl_check_3d(fig) -> tuple[bool, str]:
    """VH1 — Detect 3D projection axes."""
    try:
        from mpl_toolkits.mplot3d import Axes3D
        for ax in fig.axes:
            if isinstance(ax, Axes3D):
                return False, "3D projection axis detected — distorts proportions"
        return True, "No 3D axes found"
    except ImportError:
        return True, "mpl_toolkits not available — skipping 3D check"


def _mpl_check_colors(ax) -> tuple[bool, str]:
    """VH2 — Check for colorblind-unsafe red+green together."""
    try:
        colors = []
        for patch in ax.patches:
            colors.append(patch.get_facecolor())
        for line in ax.lines:
            colors.append(line.get_color())

        def _is_red(c):
            return c[0] > 0.6 and c[1] < 0.4 and c[2] < 0.4

        def _is_green(c):
            return c[1] > 0.5 and c[0] < 0.5 and c[2] < 0.4

        has_red   = any(_is_red(c)   for c in colors if len(c) >= 3)
        has_green = any(_is_green(c) for c in colors if len(c) >= 3)

        if has_red and has_green:
            return False, "Red + green used together — not colorblind safe"
        return True, "No obvious colorblind conflict detected"
    except Exception as e:
        return True, f"Color check skipped: {e}"


def _mpl_check_title(ax) -> tuple[bool, str]:
    """AC1 — Title must exist and be descriptive (>3 words)."""
    title = ax.get_title().strip()
    if not title:
        return False, "No chart title found"
    words = title.split()
    if len(words) < 3:
        return False, f"Title too vague: '{title}' ({len(words)} word(s))"
    return True, f"Title found: '{title}'"


def _mpl_check_legend(ax) -> tuple[bool, str]:
    """AC2 — If multiple series, a legend must exist."""
    n_series = max(len(ax.lines), len(ax.collections), 1)
    legend = ax.get_legend()
    if n_series > 1 and legend is None:
        return False, f"{n_series} series detected but no legend present"
    return True, "Legend present or single-series chart"


# ─────────────────────────────────────────────────────────────
#  IMAGE (PIL) CHECKS
# ─────────────────────────────────────────────────────────────

def _img_check_yaxis_zero(img: "Image.Image") -> tuple[bool, str]:
    """AX1 — Approximate: check if bottom-left corner is plain white/light
    (suggesting the axis baseline is at the chart edge)."""
    w, h = img.size
    region = img.crop((0, int(h * 0.85), int(w * 0.15), h))
    arr = np.array(region.convert("RGB"))
    mean_brightness = arr.mean()
    # Heuristic: very dark bottom-left suggests truncated bar baseline
    if mean_brightness < 100:
        return False, f"Bottom-left region is dark (brightness={mean_brightness:.0f}) — possible truncated axis"
    return True, f"Bottom-left brightness={mean_brightness:.0f} — axis baseline looks OK"


def _img_check_colors_pil(img: "Image.Image") -> tuple[bool, str]:
    """VH2 — Extract dominant colors; flag red+green together."""
    arr = np.array(img.convert("RGB")).reshape(-1, 3)
    # Sample every 10th pixel for speed
    sample = arr[::10]

    def _dominant_hue_family(pixels):
        families = {"red": 0, "green": 0, "blue": 0, "other": 0}
        for r, g, b in pixels:
            if r > 150 and g < 100 and b < 100:
                families["red"] += 1
            elif g > 150 and r < 100 and b < 100:
                families["green"] += 1
            elif b > 150 and r < 100 and g < 100:
                families["blue"] += 1
            else:
                families["other"] += 1
        return families

    fam = _dominant_hue_family(sample)
    if fam["red"] > 500 and fam["green"] > 500:
        return False, f"Red and green both prominent — colorblind accessibility risk"
    return True, f"Color families: R={fam['red']} G={fam['green']} B={fam['blue']}"


def _img_check_title(img: "Image.Image") -> tuple[bool, str]:
    """AC1 — Check if top strip has significant dark pixels (text presence)."""
    w, h = img.size
    top_strip = img.crop((0, 0, w, int(h * 0.12))).convert("L")
    arr = np.array(top_strip)
    dark_pixels = (arr < 100).sum()
    ratio = dark_pixels / arr.size
    if ratio > 0.01:
        return True, f"Dark pixel ratio in title zone: {ratio:.2%} — title likely present"
    return False, f"Very few dark pixels in top zone ({ratio:.2%}) — title may be missing"


def _img_check_legend(img: "Image.Image") -> tuple[bool, str]:
    """AC2 — Heuristic: right-side region often contains legend boxes."""
    w, h = img.size
    right = img.crop((int(w * 0.75), int(h * 0.1), w, int(h * 0.9))).convert("RGB")
    arr = np.array(right)
    unique_colors = len(np.unique(arr.reshape(-1, 3), axis=0))
    if unique_colors > 80:
        return True, f"Right region has {unique_colors} unique colors — legend likely present"
    return False, f"Right region has only {unique_colors} unique colors — legend may be missing"


# ─────────────────────────────────────────────────────────────
#  SEMI-AUTO: KEYWORD SCAN (works for both modes)
# ─────────────────────────────────────────────────────────────

SOURCE_KEYWORDS   = ["source", "data from", "via", "adapted from", "based on",
                     "http", "www", ".org", ".gov", ".com"]
TIMEFRAME_PATTERN = re.compile(
    r"\b(19|20)\d{2}\b"                     # 4-digit year
    r"|\bjan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec\b"  # month names
    r"|\bq[1-4]\b"                           # Q1–Q4
    r"|\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b",  # date formats
    re.IGNORECASE
)

def _semi_check_source(text: str) -> tuple[bool, str]:
    """CC1 — Keyword scan for source attribution."""
    tl = text.lower()
    for kw in SOURCE_KEYWORDS:
        if kw in tl:
            return True, f"Source keyword found: '{kw}'"
    return False, "No source attribution detected in chart text"


def _semi_check_timeframe(text: str) -> tuple[bool, str]:
    """CC2 — Regex scan for dates / timeframe indicators."""
    matches = TIMEFRAME_PATTERN.findall(text)
    if matches:
        return True, f"Timeframe indicator found: {matches[:3]}"
    return False, "No timeframe or date detected in chart text"


def _semi_check_axis_labels_text(text: str) -> tuple[bool, str]:
    """AX3 fallback — scan for common axis label patterns."""
    tl = text.lower()
    axis_hints = ["year", "month", "count", "value", "percent", "%",
                  "number", "rate", "index", "score", "total", "amount"]
    found = [h for h in axis_hints if h in tl]
    if found:
        return True, f"Axis label keywords: {found}"
    return False, "No axis label keywords found in image text"


def _semi_check_title_text(text: str) -> tuple[bool, str]:
    """AC1 fallback — check if there's a multi-word phrase near the top."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        first = lines[0]
        if len(first.split()) >= 3:
            return True, f"Likely title (first line): '{first}'"
        return False, f"First text line too short for a title: '{first}'"
    return False, "No text extracted from image"


# ─────────────────────────────────────────────────────────────
#  MANUAL PROMPT (interactive Y/N questions)
# ─────────────────────────────────────────────────────────────

MANUAL_QUESTIONS = {
    "VH3": "Does the chart type suit the data? (e.g. no pie chart with 10+ slices, no bar for continuous data)",
    "CC3": "Is the sample size or population clearly mentioned on the chart?",
    "AC3": "Can a general audience understand this chart without domain expertise?",
}

def _ask_manual(criterion_id: str,
                preloaded: dict = None,
                chart_key: str = None) -> tuple[bool, str]:
    """
    Answer a manual criterion.
    If preloaded answers are provided for this chart, use them silently.
    Otherwise fall back to interactive Y/N prompt.
    """
    if preloaded and chart_key and chart_key in preloaded:
        answer = preloaded[chart_key].get(criterion_id)
        if answer is not None:
            label = "Yes" if answer else "No"
            print(f"  [MANUAL — {criterion_id}] Auto-answered from file: {label}")
            return answer, f"Pre-loaded answer: {label}"

    # fallback: ask interactively
    question = MANUAL_QUESTIONS.get(criterion_id, "Does this criterion pass?")
    print(f"\n  [MANUAL CHECK — {criterion_id}]")
    print(f"  {textwrap.fill(question, width=70, subsequent_indent='  ')}")
    while True:
        ans = input("  Your answer (y/n): ").strip().lower()
        if ans in ("y", "yes"):
            return True, "User confirmed: Yes"
        if ans in ("n", "no"):
            return False, "User confirmed: No"
        print("  Please enter 'y' or 'n'.")


# ─────────────────────────────────────────────────────────────
#  CORE SCORER — MATPLOTLIB
# ─────────────────────────────────────────────────────────────

def vic_score_matplotlib(fig, ax, chart_name: str = "Untitled chart",
                         extra_text: str = "") -> VICResult:
    """
    Score a Matplotlib figure against the VIC framework.

    Parameters
    ----------
    fig         : matplotlib Figure object
    ax          : primary Axes object
    chart_name  : label for the report
    extra_text  : any caption / footnote text to feed into keyword checks
    """
    if not HAS_MPL:
        raise ImportError("matplotlib is required: pip install matplotlib")

    result = VICResult(chart_name=chart_name, chart_type="matplotlib")

    # Collect all text in the figure for keyword scans
    all_text = extra_text + " " + " ".join(
        t.get_text() for t in fig.findobj(matplotlib.text.Text)
    )

    auto_checks = {
        "AX1": lambda: _mpl_check_yaxis_zero(ax),
        "AX2": lambda: _mpl_check_scale_consistency(ax),
        "VH1": lambda: _mpl_check_3d(fig),
        "VH2": lambda: _mpl_check_colors(ax),
        "AC2": lambda: _mpl_check_legend(ax),
    }
    semi_checks = {
        "AX3": lambda: _mpl_check_axis_labels(ax),
        "CC1": lambda: _semi_check_source(all_text),
        "CC2": lambda: _semi_check_timeframe(all_text),
        "AC1": lambda: _mpl_check_title(ax),
    }

    _run_checks(result, auto_checks, semi_checks)
    _finalise(result)
    return result


# ─────────────────────────────────────────────────────────────
#  CORE SCORER — IMAGE FILE
# ─────────────────────────────────────────────────────────────

def vic_score_image(image_path: str, extra_text: str = "",
                    preloaded: dict = None) -> VICResult:
    """
    Score a PNG/JPG chart screenshot against the VIC framework.

    Parameters
    ----------
    image_path  : path to the chart image
    extra_text  : any caption / alt-text / surrounding text
    preloaded   : dict of pre-loaded manual answers (from manual_answers.json)
    """
    if not HAS_PIL:
        raise ImportError("Pillow and numpy are required: pip install Pillow numpy")

    img = Image.open(image_path).convert("RGB")
    chart_name = os.path.basename(image_path)
    chart_key  = os.path.splitext(chart_name)[0]
    result = VICResult(chart_name=chart_name, chart_type="image")

    all_text = extra_text

    auto_checks = {
        "AX1": lambda: _img_check_yaxis_zero(img),
        "AX2": lambda: (True, "Scale consistency check requires matplotlib metadata — skipped for image"),
        "VH1": lambda: (True, "3D detection requires metadata — skipped for image"),
        "VH2": lambda: _img_check_colors_pil(img),
        "AC2": lambda: _img_check_legend(img),
    }
    semi_checks = {
        "AX3": lambda: _semi_check_axis_labels_text(all_text),
        "CC1": lambda: _semi_check_source(all_text),
        "CC2": lambda: _semi_check_timeframe(all_text),
        "AC1": lambda: _img_check_title(img),
    }

    _run_checks(result, auto_checks, semi_checks,
                preloaded=preloaded, chart_key=chart_key)
    _finalise(result)
    return result


# ─────────────────────────────────────────────────────────────
#  SHARED INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _run_checks(result: VICResult, auto_checks: dict, semi_checks: dict,
                preloaded: dict = None, chart_key: str = None):
    """Execute all 12 criteria and populate result.criteria."""
    for cid, dim, name, penalty, method in CRITERIA_META:
        if method == "manual":
            passed, note = _ask_manual(cid, preloaded=preloaded, chart_key=chart_key)
        elif cid in auto_checks:
            passed, note = auto_checks[cid]()
        elif cid in semi_checks:
            passed, note = semi_checks[cid]()
        else:
            passed, note = True, "Check not implemented — defaulting to pass"

        result.criteria.append(CriterionResult(
            id=cid,
            dimension=dim,
            name=name,
            passed=passed,
            penalty=penalty,
            points_lost=0 if passed else penalty,
            method=method,
            note=note,
        ))


def _finalise(result: VICResult):
    """Calculate MRS, risk band, and per-dimension scores."""
    result.mrs = sum(c.points_lost for c in result.criteria)

    if result.mrs <= 30:
        result.risk_band = "LOW"
    elif result.mrs <= 60:
        result.risk_band = "MEDIUM"
    else:
        result.risk_band = "HIGH"

    for dim_key, (dim_name, max_pts) in DIMENSIONS.items():
        lost = sum(c.points_lost for c in result.criteria if c.dimension == dim_key)
        result.dimension_scores[dim_name] = {
            "lost": lost,
            "max": max_pts,
            "score": max_pts - lost,
        }


# ─────────────────────────────────────────────────────────────
#  REPORT PRINTER
# ─────────────────────────────────────────────────────────────

BAND_COLORS = {"LOW": "\033[92m", "MEDIUM": "\033[93m", "HIGH": "\033[91m"}
RESET = "\033[0m"
BOLD  = "\033[1m"

def _print_report(result: VICResult):
    band_color = BAND_COLORS.get(result.risk_band, "")
    print("\n" + "═" * 62)
    print(f"{BOLD}  VIC REPORT — {result.chart_name}{RESET}")
    print(f"  Source type : {result.chart_type}")
    print("─" * 62)

    for dim_key, (dim_name, max_pts) in DIMENSIONS.items():
        ds = result.dimension_scores[dim_name]
        bar_filled = int((ds["score"] / max_pts) * 20)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        print(f"\n  {BOLD}{dim_name}{RESET}")
        print(f"  [{bar}] {ds['score']}/{max_pts} pts")
        for c in result.criteria:
            if c.dimension != dim_key:
                continue
            status = "✓" if c.passed else "✗"
            color  = "\033[92m" if c.passed else "\033[91m"
            flag   = f"[{c.method.upper():<6}]"
            print(f"    {color}{status}{RESET} {flag} {c.name}")
            if not c.passed:
                print(f"         → {c.note}")

    print("\n" + "─" * 62)
    print(f"  {BOLD}Misleading Risk Score (MRS) : "
          f"{band_color}{result.mrs} / 100{RESET}")
    print(f"  {BOLD}Risk Band                   : "
          f"{band_color}{result.risk_band}{RESET}")
    print("═" * 62 + "\n")


# ─────────────────────────────────────────────────────────────
#  BATCH RUNNER  (score multiple charts, export CSV)
# ─────────────────────────────────────────────────────────────

def vic_batch(image_paths: list[str], output_csv: str = "vic_results.csv",
              answers_file: str = "manual_answers.json") -> list[VICResult]:
    """
    Score a list of image files and save results to CSV.
    Automatically loads manual answers from answers_file if it exists,
    so no interactive prompts are needed.

    Usage:
        charts = ["chart1.png", "chart2.png", ...]
        results = vic_batch(charts, "my_results.csv", "manual_answers.json")
    """
    import csv, json

    # Load pre-saved manual answers if available
    preloaded = None
    if os.path.exists(answers_file):
        with open(answers_file, "r") as f:
            preloaded = json.load(f)
        print(f"\n✓ Loaded manual answers from: {answers_file}")
    else:
        print(f"\n⚠ No answers file found at '{answers_file}' — will ask manually.")

    results = []
    for path in image_paths:
        print(f"\n{'─'*40}\nScoring: {path}")
        r = vic_score_image(path, preloaded=preloaded)
        r.print_report()
        results.append(r)

    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Chart", "Type", "MRS", "Risk Band",
            "Axis Integrity", "Visual Honesty",
            "Contextual Completeness", "Audience Clarity",
        ])
        for r in results:
            ds = r.dimension_scores
            writer.writerow([
                r.chart_name, r.chart_type, r.mrs, r.risk_band,
                ds["Axis Integrity"]["score"],
                ds["Visual Honesty"]["score"],
                ds["Contextual Completeness"]["score"],
                ds["Audience Clarity"]["score"],
            ])

    print(f"\n✓ Results saved to: {output_csv}")
    return results


# ─────────────────────────────────────────────────────────────
#  DEMO — runs if script is executed directly
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__" and HAS_MPL:
    print("\n" + "═"*62)
    print("  VIC DEMO — Scoring a deliberately bad Matplotlib chart")
    print("═"*62)

    fig, ax = plt.subplots(figsize=(7, 4))

    # Intentionally bad chart: truncated Y-axis, no labels, no title
    categories = ["Product A", "Product B", "Product C"]
    values = [102, 105, 108]
    bars = ax.bar(categories, values, color=["#e74c3c", "#27ae60", "#3498db"])
    ax.set_ylim(100, 110)   # ← truncated Y-axis (AX1 should FAIL)
    # No title, no axis labels, no source  (AC1, AX3, CC1 should FAIL)

    result = vic_score_matplotlib(
        fig, ax,
        chart_name="Demo — Bad Chart",
        extra_text=""   # no caption text
    )
    result.print_report()
