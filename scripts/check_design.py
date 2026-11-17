"""Check the TubeForge design system for mistakes. Standard library only.

Usage:  python scripts/check_design.py           (exit code 0 = all good)

Every failure line says FILE, what is wrong and how to fix it. Checks:
  1. tokens.css and tailwind.config.js define exactly the same tf-* colors.
  2. No hex/rgb colors outside design/tokens.css (in the guide, its JS, the Tailwind config).
  3. Classes in the guide use only allowed colors, sizes and radii (no Tailwind built-in palettes,
     no opacity modifiers like bg-tf-ok/20, no text-2xl, no rounded-xl, no shadows, only listed [arbitrary] values).
  4. Every <section data-component="x"> in guide.html has "### Component: x" in DESIGN.md, and the reverse.
  5. Accessibility basics in guide.html: every button has type=, every field has an id and a label,
     every id is unique, no inline style="" attributes.
  6. Color contrast of the token pairs listed in CONTRAST_PAIRS (WCAG 2.1 ratios).
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design"
TOKENS = DESIGN / "tokens.css"
CONFIG = DESIGN / "tailwind.config.js"
GUIDE = DESIGN / "guide.html"
DOC = DESIGN / "DESIGN.md"
SCANNED_FOR_COLORS = [GUIDE, CONFIG, DESIGN / "guide.js", DESIGN / "tubeforge-ui.js"]

# Arbitrary Tailwind values allowed in recipes. Add here only with a reason in DESIGN.md.
ALLOWED_ARBITRARY = {"aspect-[9/16]", "min-w-[480px]", "min-w-[560px]"}
ALLOWED_ARBITRARY_VARIANTS = ("aria-[current=page]:", "aria-[current=step]:", "aria-[invalid=true]:")
TEXT_SIZES = {"xs", "sm", "base", "md", "lg", "xl"}
TAILWIND_PALETTES = (
    "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|"
    "indigo|violet|purple|fuchsia|pink|rose|white|black"
)
COLOR_PREFIXES = "bg|text|border|border-[trblxy]|divide|ring|outline|accent|decoration|fill|stroke|from|via|to|caret|placeholder"

# (foreground, background, minimum ratio, why). 4.5 = body text, 3.0 = large text / control edges.
CONTRAST_PAIRS = [
    ("tf-text", "tf-bg", 4.5, "body text"),
    ("tf-text", "tf-surface", 4.5, "text in panels"),
    ("tf-text", "tf-raised", 4.5, "text in dialogs"),
    ("tf-muted", "tf-bg", 4.5, "secondary text"),
    ("tf-muted", "tf-surface", 4.5, "secondary text in panels"),
    ("tf-muted", "tf-raised", 4.5, "secondary text in dialogs"),
    ("tf-faint", "tf-surface", 3.0, "placeholders and waiting stages"),
    ("tf-faint", "tf-input", 3.0, "placeholders"),
    ("tf-accent-ink", "tf-accent", 4.5, "primary button label"),
    ("tf-accent", "tf-accent-soft", 4.5, "current nav item"),
    ("tf-accent", "tf-bg", 3.0, "focus ring"),
    ("tf-danger-ink", "tf-danger", 4.5, "danger button label"),
    ("tf-ok", "tf-ok-soft", 4.5, "ok badge"),
    ("tf-warn", "tf-warn-soft", 4.5, "warn badge"),
    ("tf-bad", "tf-bad-soft", 4.5, "error badge and notice title"),
    ("tf-info", "tf-info-soft", 4.5, "info badge"),
    ("tf-text", "tf-bad-soft", 4.5, "notice body"),
    ("tf-text", "tf-warn-soft", 4.5, "notice body"),
    ("tf-bad", "tf-bg", 4.5, "field error text"),
    ("tf-line-strong", "tf-input", 3.0, "text field edge"),
    ("tf-line-strong", "tf-bg", 3.0, "secondary button edge"),
]

errors: list[str] = []


def fail(path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def css_tokens() -> dict[str, str]:
    text = TOKENS.read_text()
    return dict(re.findall(r"--(tf-[a-z0-9-]+):\s*([^;]+);", text))


def check_token_sync(tokens: dict[str, str]) -> None:
    config = CONFIG.read_text()
    config_colors = set(re.findall(r'"(tf-[a-z0-9-]+)":\s*"var\(--\1\)"', config))
    css_colors = {name for name, value in tokens.items() if value.strip().startswith(("#", "rgb"))}
    for name in sorted(css_colors - config_colors):
        fail(CONFIG, f'color token {name} is in tokens.css but missing here. Add:  "{name}": "var(--{name})",')
    for name in sorted(config_colors - css_colors):
        fail(TOKENS, f"color {name} is used in tailwind.config.js but not defined. Add  --{name}: #......;  to :root")


def check_no_raw_colors() -> None:
    pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(")
    for path in SCANNED_FOR_COLORS:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for match in pattern.finditer(line):
                if match.group(0).startswith("#") and re.search(r'href="#|id="|getAttribute|\.slice', line):
                    continue
                fail(path, f"line {number}: raw color '{match.group(0)}'. Use a tf-* class, or add a token to design/tokens.css")


def check_classes() -> None:
    html = GUIDE.read_text()
    bad_palette = re.compile(rf"^(?:{COLOR_PREFIXES})-(?:{TAILWIND_PALETTES})(?:-\d+)?$")
    for number, line in enumerate(html.splitlines(), 1):
        for attr in re.findall(r'class="([^"]*)"', line):
            for raw in attr.split():
                cls = raw
                for variant in ALLOWED_ARBITRARY_VARIANTS:
                    cls = cls.replace(variant, "")
                base = cls.split(":")[-1]
                where = f"line {number}: class '{raw}'"
                if bad_palette.match(base):
                    fail(GUIDE, f"{where} uses a Tailwind palette color. Use tf-* colors only (see Colors in guide.html)")
                if re.match(rf"^(?:{COLOR_PREFIXES})-tf-[a-z-]+/\d+$", base):
                    fail(GUIDE, f"{where} has an opacity modifier. Use a *-soft token instead")
                m = re.match(r"^text-(\d?xl|\[.*\])$", base)
                if m and base not in {"text-xl"}:
                    fail(GUIDE, f"{where} is not in the type scale. Use text-xs, -sm, -base, -md, -lg or -xl")
                if re.match(r"^rounded(-[trbl]{1,2})?(-(xl|2xl|3xl))?$", base) and base not in {"rounded"}:
                    if base.endswith(("xl",)):
                        fail(GUIDE, f"{where} is not an allowed radius. Use rounded-sm, -md, -lg or -full")
                if base == "rounded":
                    fail(GUIDE, f"{where}: plain 'rounded' does nothing here. Use rounded-sm, -md, -lg or -full")
                if base.startswith("shadow"):
                    fail(GUIDE, f"{where}: shadows are not used. Separate with a border or tf-raised instead")
                if "[" in cls and base not in ALLOWED_ARBITRARY:
                    fail(GUIDE, f"{where} uses an arbitrary value. Use a scale value, or add it to ALLOWED_ARBITRARY with a reason")


def check_component_sync() -> None:
    html = GUIDE.read_text()
    doc = DOC.read_text()
    in_guide = re.findall(r'<section[^>]*data-component="([a-z0-9-]+)"', html)
    in_doc = re.findall(r"^### Component: ([a-z0-9-]+)\s*$", doc, flags=re.M)
    for name in sorted(set(in_guide) - set(in_doc)):
        fail(DOC, f"component '{name}' is in guide.html but has no '### Component: {name}' section")
    for name in sorted(set(in_doc) - set(in_guide)):
        fail(GUIDE, f"DESIGN.md documents '{name}' but there is no <section data-component=\"{name}\" id=\"{name}\">")
    for name in in_guide:
        if not re.search(rf'<section id="{name}" data-component="{name}"', html):
            fail(GUIDE, f"section '{name}' must start with <section id=\"{name}\" data-component=\"{name}\"")
    for name in set(n for n in in_guide if in_guide.count(n) > 1):
        fail(GUIDE, f"component '{name}' appears more than once")


class A11yParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.label_for: set[str] = set()
        self.fields: list[tuple[int, dict[str, str | None]]] = []
        self.buttons_without_type: list[int] = []
        self.inline_styles: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        line = self.getpos()[0]
        if a.get("id"):
            self.ids.append(a["id"] or "")
        if "style" in a:
            self.inline_styles.append(line)
        if tag == "label" and a.get("for"):
            self.label_for.add(a["for"] or "")
        if tag == "button" and "type" not in a:
            self.buttons_without_type.append(line)
        if tag in {"input", "select", "textarea"} and a.get("type") != "hidden":
            self.fields.append((line, a))


def check_accessibility() -> None:
    parser = A11yParser()
    parser.feed(GUIDE.read_text())
    for line in parser.buttons_without_type:
        fail(GUIDE, f"line {line}: <button> without type=. Add type=\"button\" (or type=\"submit\" in a form)")
    for line in parser.inline_styles:
        fail(GUIDE, f"line {line}: inline style=\"\". Use Tailwind classes or a token")
    for line, a in parser.fields:
        field_id = a.get("id")
        if not field_id:
            fail(GUIDE, f"line {line}: form field without id")
        elif field_id not in parser.label_for and not a.get("aria-label"):
            fail(GUIDE, f"line {line}: field '{field_id}' has no <label for=\"{field_id}\">")
    for dup in sorted({i for i in parser.ids if parser.ids.count(i) > 1}):
        fail(GUIDE, f"id '{dup}' is used more than once; ids must be unique on a page")


def luminance(color: str) -> float:
    color = color.strip()
    if color.startswith("#"):
        h = color[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    else:
        channels = [int(v) / 255 for v in re.findall(r"\d+", color)[:3]]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check_contrast(tokens: dict[str, str], report: bool) -> None:
    for fg, bg, minimum, why in CONTRAST_PAIRS:
        if fg not in tokens or bg not in tokens:
            fail(TOKENS, f"contrast pair {fg} on {bg} refers to a missing token")
            continue
        ratio = contrast(tokens[fg], tokens[bg])
        if report:
            print(f"  {ratio:5.2f}  {'ok ' if ratio >= minimum else 'LOW'}  {fg} on {bg} (needs {minimum}, {why})")
        if ratio < minimum:
            fail(TOKENS, f"{fg} on {bg} is {ratio:.2f}:1, needs {minimum}:1 ({why}). Lighten the text or darken the background")


def main(argv: list[str]) -> int:
    tokens = css_tokens()
    check_token_sync(tokens)
    check_no_raw_colors()
    check_classes()
    check_component_sync()
    check_accessibility()
    check_contrast(tokens, report="--contrast" in argv)
    if errors:
        print(f"Design check FAILED ({len(errors)} problems):")
        for error in errors:
            print(" -", error)
        return 1
    print("Design check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
