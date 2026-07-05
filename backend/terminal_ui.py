from __future__ import annotations

import json
import os
from typing import Any

from rich.console import Console, Group
from rich.json import JSON
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
    "fg": "#ebdbb2",
    "muted": "#928374",
    "red": "#fb4934",
    "green": "#b8bb26",
    "yellow": "#fabd2f",
    "blue": "#83a598",
    "purple": "#d3869b",
    "aqua": "#8ec07c",
    "orange": "#fe8019",
}

theme = Theme(
    {
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


def render_json(data: Any) -> JSON | Pretty:
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
        return value
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


def _tool_call_text(name: str, arguments: dict[str, Any]) -> tuple[str, str]:
    if name == "get_vep_consequence":
        variant = arguments.get("variant", "the variant")
        return "Checking Ensembl VEP", f"Looking up the predicted biological effect for {variant}."
    if name == "get_clinvar_summary":
        gene = arguments.get("gene_symbol", "the gene")
        change = arguments.get("protein_change_short", "the protein change")
        return "Searching ClinVar", f"Checking clinical records for {gene} {change}."
    return "Working", f"Running {_clean_label(name)}."


def _vep_summary(result: dict[str, Any]) -> Table | Text:
    if result.get("error"):
        return Text(result.get("message", "The variant lookup did not return a usable result."), style="error")

    position = None
    if result.get("genomic_start") and result.get("genomic_end"):
        position = (
            result["genomic_start"]
            if result["genomic_start"] == result["genomic_end"]
            else f"{result['genomic_start']} to {result['genomic_end']}"
        )

    return _details_table(
        [
            ("Gene", result.get("gene_symbol")),
            ("Effect", result.get("consequence", "").replace("_", " ") if result.get("consequence") else None),
            ("Protein", result.get("protein_change")),
            ("Short form", result.get("protein_change_short")),
            ("Position", position),
        ]
    )


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


def print_banner() -> None:
    title = Text("VepClin MCP", style="app.title")
    title.append("  ", style="app.subtitle")
    title.append("variant annotation chat", style="app.subtitle")
    body = Group(
        title,
        Text(
            "Ask about genomic variants using HGVS notation or familiar names like BRAF V600E.",
            style="hint",
        ),
        Text("Type /help for tips, /clear to reset context, or /exit to quit.", style="hint"),
    )
    console.print(
        Panel(
            body,
            border_style=GRUVBOX["yellow"],
            padding=(1, 2),
            style=GRUVBOX["fg"],
        )
    )


def print_help() -> None:
    tips = Table.grid(padding=(0, 2))
    tips.add_column(style="tool", no_wrap=True)
    tips.add_column(style="hint")
    tips.add_row("Best input", "chr7:g.140753336A>T or a known shorthand like BRAF V600E")
    tips.add_row("Complex variants", "Use exact notation from a lab report or ClinVar page")
    tips.add_row("Commands", "/help, /clear, /exit")
    console.print(Panel(tips, title="Tips", border_style=GRUVBOX["blue"], padding=(1, 2)))


def print_answer(content: str) -> None:
    console.print(
        Panel(
            Markdown(content or "_No answer returned._"),
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
            render_json(detail) if isinstance(detail, (dict, list)) else Text(str(detail), style="error"),
            title=title,
            title_align="left",
            border_style=GRUVBOX["red"],
            padding=(1, 2),
        )
    )


def print_retry(attempt: int, detail: Any, backoff_seconds: int, title: str = "OpenRouter retry") -> None:
    body = Group(
        Text(f"Attempt {attempt} failed.", style="retry"),
        render_json(detail) if isinstance(detail, (dict, list)) else Text(str(detail), style="hint"),
        Text(f"Retrying in {backoff_seconds} seconds...", style="hint"),
    )
    console.print(Panel(body, title=title, border_style=GRUVBOX["orange"], padding=(1, 2)))


def print_tool_call(name: str, arguments: dict[str, Any]) -> None:
    title, message = _tool_call_text(name, arguments)
    console.print(
        Panel(
            Text(message, style="answer"),
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
        body = Text(_clean_value(data), style="hint")
    else:
        body = Text("ready", style="hint")

    console.print(Panel(body, title=title, title_align="left", border_style=GRUVBOX["aqua"], padding=(1, 2)))


def print_clear_notice() -> None:
    console.print(Rule("conversation reset", style=GRUVBOX["muted"]))
