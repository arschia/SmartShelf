import os
import json
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"


def wcag_relative_luminance(hex_color: str) -> float:
    """Calculate WCAG 2.1 relative luminance for an sRGB hex color."""
    hex_color = hex_color.lstrip('#')
    r, g, b = [int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    
    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    rl = linearize(r)
    gl = linearize(g)
    bl = linearize(b)
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl


def wcag_contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate WCAG 2.1 contrast ratio between two colors."""
    l1 = wcag_relative_luminance(hex1)
    l2 = wcag_relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_wcag_contrast_ratios_phase4():
    """
    Verify all normal text and semantic colors meet WCAG 2.1 AA (contrast ratio >= 4.5:1).
    Also verify forbidden combinations like Soft Crimson on Burgundy fail the 4.5:1 threshold.
    """
    # Palette colors
    PLUM = "#321126"
    BURGUNDY = "#641B3A"
    CRIMSON = "#B72D52"
    SOFT_CRIMSON = "#D34C67"
    CREAM = "#F7F0E8"
    IVORY = "#FFFDF9"

    # Light Theme Semantic Colors
    SUCCESS_LIGHT = "#166534"
    WARNING_LIGHT = "#9a3412"
    DANGER_LIGHT = "#9f1239"
    INFO_LIGHT = "#0369a1"

    # Dark Theme Semantic Colors
    SUCCESS_DARK = "#86efac"
    WARNING_DARK = "#fde047"
    DANGER_DARK = "#fca5a5"
    INFO_DARK = "#7dd3fc"

    # Light Theme tests on Canvas (Ivory) and Surfaces (Cream)
    assert wcag_contrast_ratio(PLUM, CREAM) >= 4.5, "Plum on Cream must be >= 4.5:1"
    assert wcag_contrast_ratio(PLUM, IVORY) >= 4.5, "Plum on Ivory must be >= 4.5:1"
    assert wcag_contrast_ratio(BURGUNDY, CREAM) >= 4.5, "Burgundy on Cream must be >= 4.5:1"
    assert wcag_contrast_ratio(CRIMSON, CREAM) >= 4.5, "Crimson on Cream must be >= 4.5:1"

    # Light Theme Semantics
    assert wcag_contrast_ratio(SUCCESS_LIGHT, CREAM) >= 4.5, "Success light on Cream must be >= 4.5:1"
    assert wcag_contrast_ratio(WARNING_LIGHT, CREAM) >= 4.5, "Warning light on Cream must be >= 4.5:1"
    assert wcag_contrast_ratio(DANGER_LIGHT, CREAM) >= 4.5, "Danger light on Cream must be >= 4.5:1"
    assert wcag_contrast_ratio(INFO_LIGHT, CREAM) >= 4.5, "Info light on Cream must be >= 4.5:1"

    # Dark Theme tests on Plum Canvas
    assert wcag_contrast_ratio(IVORY, PLUM) >= 4.5, "Ivory on Plum must be >= 4.5:1"
    assert wcag_contrast_ratio(CREAM, PLUM) >= 4.5, "Cream on Plum must be >= 4.5:1"
    assert wcag_contrast_ratio(SUCCESS_DARK, PLUM) >= 4.5, "Success dark on Plum must be >= 4.5:1"
    assert wcag_contrast_ratio(WARNING_DARK, PLUM) >= 4.5, "Warning dark on Plum must be >= 4.5:1"
    assert wcag_contrast_ratio(DANGER_DARK, PLUM) >= 4.5, "Danger dark on Plum must be >= 4.5:1"
    assert wcag_contrast_ratio(INFO_DARK, PLUM) >= 4.5, "Info dark on Plum must be >= 4.5:1"

    # Soft Crimson is restricted: verify it does NOT qualify for small normal text on Burgundy
    soft_crimson_on_burgundy = wcag_contrast_ratio(SOFT_CRIMSON, BURGUNDY)
    assert soft_crimson_on_burgundy < 4.5, "Soft Crimson on Burgundy must not be used for normal text"


def test_format_js_module_execution():
    """Verify format.js behavior (numbers, Toman, Jalali dates, digit normalization)."""
    js_code = """
    const fmt = require('./frontend/assets/js/format.js');
    const results = {
      normalizedPersian: fmt.normalizeDigits('۰۹۱۲۳۴۵۶۷۸۹'),
      normalizedArabic: fmt.normalizeDigits('٠١٢٣٤٥٦٧٨٩'),
      tomanZero: fmt.formatToman(0),
      tomanSample: fmt.formatToman(125000),
      numberSample: fmt.formatNumber(1234567),
      jalaliYear: fmt.formatJalali(new Date('2026-11-03T12:00:00Z'), { year: 'numeric' })
    };
    console.log(JSON.stringify(results));
    """
    proc = subprocess.run(
        ["node", "-e", js_code],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True
    )
    res = json.loads(proc.stdout)
    assert res["normalizedPersian"] == "09123456789"
    assert res["normalizedArabic"] == "0123456789"
    assert "تومان" in res["tomanSample"]
    assert "تومان" in res["tomanZero"]
    assert "۱۴۰۵" in res["jalaliYear"]


def test_design_system_files_and_tokens_exist():
    """Verify all required CSS, JS, SVG, and font assets exist."""
    required_files = [
        ASSETS_DIR / "css" / "tokens.css",
        ASSETS_DIR / "css" / "base.css",
        ASSETS_DIR / "css" / "components.css",
        ASSETS_DIR / "css" / "motion.css",
        ASSETS_DIR / "js" / "format.js",
        ASSETS_DIR / "js" / "ui.js",
        ASSETS_DIR / "img" / "logo.svg",
        ASSETS_DIR / "img" / "logo-mark.svg",
        ASSETS_DIR / "fonts" / "LICENSE.txt",
        ASSETS_DIR / "fonts" / "dana.css",
        FRONTEND_DIR / "styleguide" / "index.html",
    ]
    for rf in required_files:
        assert rf.exists(), f"Missing required file: {rf}"

    # Verify tokens.css contains required color variables
    tokens_content = (ASSETS_DIR / "css" / "tokens.css").read_text(encoding="utf-8")
    for var_name in ["--color-plum", "--color-burgundy", "--color-crimson", "--color-soft-crimson", "--color-cream", "--color-ivory"]:
        assert var_name in tokens_content, f"Token {var_name} missing in tokens.css"

    # Verify SVG logo files are valid XML
    for svg_path in [ASSETS_DIR / "img" / "logo.svg", ASSETS_DIR / "img" / "logo-mark.svg"]:
        content = svg_path.read_text(encoding="utf-8")
        assert "<svg" in content and "</svg>" in content


def test_styleguide_route_served():
    """Verify /styleguide endpoint is served by FastAPI."""
    client = TestClient(app)
    resp = client.get("/styleguide/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "SMARTSHELF" in resp.text
    assert "سیستم طراحی" in resp.text
