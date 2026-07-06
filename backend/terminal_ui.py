from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.json import JSON
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme


GRUVBOX = {
    "bg": "#282828",
    "bg_soft": "#3c3836",
    "fg_dark": "#1d2021",
    "fg": "#ebdbb2",
    "muted": "#928374",
    "red": "#fb4934",
    "green": "#b8bb26",
    "yellow": "#fabd2f",
    "blue": "#83a598",
    "purple": "#d3869b",
    "purple_dark": "#b16286",
    "aqua": "#8ec07c",
    "orange": "#fe8019",
    "indigo": "#1A0044",
}

theme = Theme(
    {
        "app.command": f"bold {GRUVBOX['orange']}",
        "app.label": f"bold {GRUVBOX['fg']}",
        "app.title": f"bold {GRUVBOX['yellow']}",
        "app.subtitle": GRUVBOX["muted"],
        "answer": GRUVBOX["fg"],
        "error": f"bold {GRUVBOX['red']}",
        "hint": GRUVBOX["muted"],
        "mcp": GRUVBOX["aqua"],
        "retry": GRUVBOX["orange"],
        "tool": GRUVBOX["blue"],
        "user": f"bold {GRUVBOX['purple']}",
    }
)

console = Console(theme=theme, highlight=False)

MASCOT_PIXELS = (
    ("accent", None, "body", None, "body", None, "accent"),
    ("accent","body", "body", "body", "body", "body", "body", "body", "accent"),
    ("body", "eye", "body", "accent", "body", "eye", "body"),
    ("body", "body", "body", "body", "body", None),
)

MASCOT_BLINK_PIXELS = (
    ("accent", None, "body", None, "body", None, "accent"),
    ("accent","body", "body", "body", "body", "body", "body", "body", "accent"),
    ("body", "body", "body", "accent", "body", "body", "body"),
    ("body", "body", "body", "body", "body", None),
)

MASCOT_PERK_PIXELS = (
    ("body", "body", "body", "body", "body", None),
    ("body", "eye", "body", "accent", "body", "eye", "body"),
    ("accent","body", "body", "body", "body", "body", "body", "body", "accent"),
    ("accent", None, "body", None, "body", None, "accent"),
)

MASCOT_COLORS = {
    "body": GRUVBOX["purple"],
    "eye": GRUVBOX["indigo"],
    "accent": GRUVBOX["purple_dark"],
}

EMOJI_RE = re.compile(
    "["
    "\U0001f1e6-\U0001f1ff"
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\u2600-\u26ff"
    "\u2700-\u27bf"
    "]+",
    flags=re.UNICODE,
)

VARIATION_SELECTOR_RE = re.compile("[\ufe0e\ufe0f]")


def strip_emojis(value: str) -> str:
    without_emoji = EMOJI_RE.sub("", value)
    return VARIATION_SELECTOR_RE.sub("", without_emoji)


def _sanitize_display_data(data: Any) -> Any:
    if isinstance(data, str):
        return strip_emojis(data)
    if isinstance(data, list):
        return [_sanitize_display_data(item) for item in data]
    if isinstance(data, dict):
        return {key: _sanitize_display_data(value) for key, value in data.items()}
    return data


def render_json(data: Any) -> JSON | Pretty:
    data = _sanitize_display_data(data)
    try:
        return JSON(json.dumps(data, indent=2, default=str))
    except TypeError:
        return Pretty(data, expand_all=True)


def _clean_label(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def _clean_value(value: Any) -> str:
    if value is None:
        return "not reported"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return strip_emojis(value)
    return str(value)


def _short_list(values: list[Any], limit: int = 5) -> str:
    cleaned = [_clean_value(value) for value in values if value]
    if not cleaned:
        return "not reported"
    shown = cleaned[:limit]
    suffix = f" and {len(cleaned) - limit} more" if len(cleaned) > limit else ""
    return ", ".join(shown) + suffix


def _details_table(rows: list[tuple[str, Any]]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="tool", no_wrap=True)
    table.add_column(style="answer")
    for label, value in rows:
        table.add_row(label, _clean_value(value))
    return table


def _mascot_lines(pixels: tuple[tuple[str | None, ...], ...] = MASCOT_PIXELS) -> list[Text]:
    lines = []
    for row in pixels:
        line = Text()
        for pixel in row:
            if pixel is None:
                line.append("  ")
            else:
                line.append("\u2588\u2588", style=MASCOT_COLORS[pixel])
        lines.append(line)
    return lines


def _mascot(pixels: tuple[tuple[str | None, ...], ...] = MASCOT_PIXELS) -> Text:
    mascot = Text()
    mascot.append("\n")
    lines = _mascot_lines(pixels)
    for index, line in enumerate(lines):
        mascot.append_text(line)
        if index < len(lines) - 1:
            mascot.append("\n")
    return mascot


def _banner_body(
    title: Text,
    model: str,
    build: str,
    transcript_scope: str,
    mascot_pixels: tuple[tuple[str | None, ...], ...] = MASCOT_PIXELS,
) -> Table:
    intro = Table.grid(padding=(0, 0))
    intro.add_column()
    intro.add_row(title)
    intro.add_row(Text(model, style="tool"))
    intro.add_row(Text(""))
    intro.add_row(Text("Ask about variants using supported HGVS notation", style="hint"))
    intro.add_row(
        Text.assemble(
            ("Type ", "hint"),
            ("/help", "app.command"),
            (" to get started", "hint"),
        )
    )

    left = Table.grid(expand=True, padding=(0, 0))
    left.add_column()
    if console.width >= 96:
        left.add_column(ratio=1)
        left.add_column(justify="center", no_wrap=True)
        left.add_column(ratio=1)
        left.add_row(intro, "", _mascot(mascot_pixels), "")
    else:
        left.add_row(intro)

    details = Table.grid(padding=(0, 0))
    details.add_column()
    details.add_row(Text.assemble(("Build:", "app.label"), (f" {build}", "hint")))
    details.add_row(Text.assemble(("Transcripts:", "app.label"), (f" {transcript_scope}", "hint")))
    details.add_row(Text(""))
    details.add_row(Text("Supported HGVS:", style="app.label"))
    details.add_row(Text.assemble(("g.", "app.command"), (" (e.g. chr7:g.140753336A>T)", "hint")))
    details.add_row(Text.assemble(("c.", "app.command"), (" (e.g. NM_004333.6:c.1799T>A)", "hint")))

    right = Table.grid(expand=True, padding=(0, 4))
    right.add_column(ratio=1)
    right.add_row(details)

    body = Table(
        show_header=False,
        show_edge=False,
        box=box.MINIMAL,
        border_style="hint",
        pad_edge=False,
        padding=(0, 2),
        expand=True,
    )
    body.add_column(ratio=3)
    body.add_column(ratio=2)
    body.add_row(left, right)
    return body


def _banner_panel(
    title: Text,
    model: str,
    build: str,
    transcript_scope: str,
    mascot_pixels: tuple[tuple[str | None, ...], ...] = MASCOT_PIXELS,
) -> Panel:
    return Panel(
        _banner_body(title, model, build, transcript_scope, mascot_pixels),
        border_style=GRUVBOX["yellow"],
        padding=(0, 2),
    )


def _transcript_table(transcripts: list[dict]) -> Table:
    table = Table(title="All transcripts", show_lines=False)
    table.add_column("Transcript", style="tool", no_wrap=True)
    table.add_column("Consequence", style="answer")
    table.add_column("Protein change", style="answer")
    table.add_column("Impact", style="answer")
    table.add_column("SIFT", style="answer")
    table.add_column("PolyPhen", style="answer")

    for tr in transcripts:
        table.add_row(
            _clean_value(tr.get("transcript_id")),
            _clean_value(tr.get("consequence")),
            _clean_value(tr.get("protein_change")),
            _clean_value(tr.get("impact")),
            _clean_value(tr.get("sift_prediction")),
            _clean_value(tr.get("polyphen_prediction")),
        )
    return table

def _tool_call_text(name: str, arguments: dict[str, Any]) -> tuple[str, str]:
    if name == "get_vep_consequence":
        variant = arguments.get("variant", "the variant")
        return "Checking Ensembl VEP", f"Looking up the predicted biological effect for {variant}."
    if name == "get_clinvar_summary":
        gene = arguments.get("gene_symbol", "the gene")
        change = arguments.get("protein_change_short", "the protein change")
        return "Searching ClinVar", f"Checking clinical records for {gene} {change}."
    return "Working", f"Running {_clean_label(name)}."


def _vep_summary(result: dict[str, Any]) -> Table | Text | Group:
    if result.get("error"):
        return Text(result.get("message", "The variant lookup did not return a usable result."), style="error")

    position = None
    if result.get("genomic_start") and result.get("genomic_end"):
        position = (
            result["genomic_start"]
            if result["genomic_start"] == result["genomic_end"]
            else f"{result['genomic_start']} to {result['genomic_end']}"
        )

    primary_table = _details_table(
        [
            ("Gene", result.get("gene_symbol")),
            ("Input", result.get("input_hgvs")),
            ("HGVS format", result.get("hgvs_format")),
            ("Effect", result.get("consequence", "").replace("_", " ") if result.get("consequence") else None),
            ("Protein", result.get("protein_change")),
            ("Short form", result.get("protein_change_short")),
            ("Position", position),
            ("Impact", result.get("impact")),
            ("SIFT", result.get("sift_prediction")),
            ("PolyPhen", result.get("polyphen_prediction")),
        ]
    )

    if result.get("transcripts"):
        return Group(primary_table, _transcript_table(result["transcripts"]))

    return primary_table


def _clinvar_summary(result: dict[str, Any]) -> Table | Text:
    if not result.get("found"):
        return Text("No ClinVar matches were found for this gene and protein change.", style="hint")

    matches = result.get("matches") or []
    first = matches[0] if matches else {}
    traits = (
        first.get("clinical_impact_traits")
        or first.get("oncogenicity_traits")
        or first.get("germline_traits")
        or []
    )

    return _details_table(
        [
            ("Matches", f"{len(matches)} found"),
            ("Top record", first.get("title")),
            ("Germline", first.get("germline_classification")),
            ("Clinical impact", first.get("clinical_impact_classification")),
            ("Oncogenicity", first.get("oncogenicity_classification")),
            ("Traits", _short_list(traits)),
            ("ClinVar ID", first.get("variation_id")),
        ]
    )


def _tool_result_content(name: str, result: Any) -> tuple[str, Table | Text | Pretty]:
    if isinstance(result, dict):
        if name == "get_vep_consequence":
            return "Variant consequence", _vep_summary(result)
        if name == "get_clinvar_summary":
            return "ClinVar summary", _clinvar_summary(result)
    return "Tool result", Pretty(result, expand_all=True)


def print_banner(
    model: str = "unknown",
    build: str = "GRCh38",
    transcript_scope: str = "MANE Select",
    animate: bool = True,
) -> None:
    title = Text("VepClin MCP", style="app.title")
    title.append("  ", style="app.subtitle")
    title.append("variant annotation chat", style="app.subtitle")
    if not animate or not console.is_terminal:
        console.print(_banner_panel(title, model, build, transcript_scope))
        return

    frames = (MASCOT_PIXELS, MASCOT_BLINK_PIXELS, MASCOT_PIXELS, MASCOT_PERK_PIXELS, MASCOT_PIXELS)
    with Live(
        _banner_panel(title, model, build, transcript_scope, frames[0]),
        console=console,
        refresh_per_second=12,
        transient=False,
        auto_refresh=False,
    ) as live:
        for frame in frames[1:]:
            time.sleep(0.20)
            live.update(_banner_panel(title, model, build, transcript_scope, frame), refresh=True)


def print_help() -> None:
    tips = Table.grid(padding=(0, 2))
    tips.add_column(style="tool", no_wrap=True)
    tips.add_column(style="hint")
    tips.add_row("Genomic HGVS", "e.g. chr7:g.140753336A>T")
    tips.add_row("Coding HGVS", "Use a transcript accession, e.g. NM_004333.6:c.1799T>A")
    tips.add_row("Protein shorthand", "Known changes like BRAF V600E can be checked in ClinVar")
    tips.add_row("Complex variants", "Use exact HGVS notation from a lab report or ClinVar page")
    tips.add_row("/batch", "Choose a VCF file and summarize multiple variants")
    tips.add_row("/build", "Choose GRCh38 or GRCh37 for VEP lookups")
    tips.add_row("/transcripts", "Choose MANE Select only or show all transcript consequences")
    tips.add_row("/clear", "Reset the conversation context")
    tips.add_row("/exit or /quit", "Quit VepClin")
    console.print(Panel(tips, title="Tips", border_style=GRUVBOX["blue"], padding=(1, 2)))


def print_setting_change(title: str, rows: list[tuple[str, Any]]) -> None:
    console.print(
        Panel(
            _details_table(rows),
            title=title,
            title_align="left",
            border_style=GRUVBOX["yellow"],
            padding=(1, 2),
        )
    )


def print_answer(content: str) -> None:
    content = strip_emojis(content or "_No answer returned._")
    console.print(
        Panel(
            Markdown(content),
            title="VepClin",
            title_align="left",
            border_style=GRUVBOX["green"],
            padding=(1, 2),
            style="answer",
        )
    )


def print_error(title: str, detail: Any) -> None:
    console.print(
        Panel(
            render_json(detail) if isinstance(detail, (dict, list)) else Text(strip_emojis(str(detail)), style="error"),
            title=title,
            title_align="left",
            border_style=GRUVBOX["red"],
            padding=(1, 2),
        )
    )


def print_retry(attempt: int, detail: Any, backoff_seconds: int, title: str = "OpenRouter retry") -> None:
    body = Group(
        Text(f"Attempt {attempt} failed.", style="retry"),
        render_json(detail) if isinstance(detail, (dict, list)) else Text(strip_emojis(str(detail)), style="hint"),
        Text(f"Retrying in {backoff_seconds} seconds...", style="hint"),
    )
    console.print(Panel(body, title=title, border_style=GRUVBOX["orange"], padding=(1, 2)))


def print_tool_call(name: str, arguments: dict[str, Any]) -> None:
    title, message = _tool_call_text(name, arguments)
    console.print(
        Panel(
            Text(strip_emojis(message), style="answer"),
            title=title,
            title_align="left",
            border_style=GRUVBOX["blue"],
            padding=(1, 2),
        )
    )


def print_tool_result(name: str, result: Any) -> None:
    title, content = _tool_result_content(name, result)
    console.print(
        Panel(
            content,
            title=title,
            title_align="left",
            border_style=GRUVBOX["aqua"],
            padding=(1, 2),
        )
    )


def print_server_event(title: str, data: Any | None = None) -> None:
    if os.environ.get("VEPCLIN_EMBEDDED_CHAT") == "1":
        return

    if title.endswith(" input") and isinstance(data, dict):
        tool_name = title.removesuffix(" input")
        print_tool_call(tool_name, data)
        return

    if title.endswith(" output"):
        tool_name = title.removesuffix(" output")
        print_tool_result(tool_name, data)
        return

    if isinstance(data, dict):
        body = _details_table([(_clean_label(key), value) for key, value in data.items()])
    elif data is not None:
        body = Text(strip_emojis(_clean_value(data)), style="hint")
    else:
        body = Text("ready", style="hint")

    console.print(Panel(body, title=title, title_align="left", border_style=GRUVBOX["aqua"], padding=(1, 2)))


def print_clear_notice() -> None:
    console.print(Rule("conversation reset", style=GRUVBOX["muted"]))

def print_batch_results(results: list[dict]) -> None:
    table = Table(title=f"Batch results ({len(results)} variants)")
    table.add_column("Input", style="tool", no_wrap=True)
    table.add_column("Gene", style="answer")
    table.add_column("Consequence", style="answer")
    table.add_column("Protein", style="answer")
    table.add_column("Impact", style="answer")
    table.add_column("ClinVar", style="answer")

    for row in results:
        clinvar = row.get("clinvar", {})
        if clinvar.get("found") and clinvar.get("matches"):
            top = clinvar["matches"][0]
            clinvar_summary = (
                top.get("germline_classification")
                or top.get("oncogenicity_classification")
                or top.get("clinical_impact_classification")
                or "present, unclassified"
            )
        else:
            clinvar_summary = "not found"

        table.add_row(
            _clean_value(row.get("input")),
            _clean_value(row.get("gene_symbol")),
            _clean_value(row.get("consequence", "").replace("_", " ") if row.get("consequence") else None),
            _clean_value(row.get("protein_change_short")),
            _clean_value(row.get("impact")),
            _clean_value(clinvar_summary),
        )

    console.print(Panel(table, title="Batch VCF", border_style=GRUVBOX["aqua"], padding=(1, 2)))
