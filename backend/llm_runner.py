from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastmcp.client import Client
from rich.prompt import Prompt

import questionary
from mcp_server import client as variant_client_instance
from mcp_server import mcp
from session_config import session_config
from terminal_ui import print_batch_results

from exporter import (
    export_to_csv,
    export_to_tsv,
    export_annotated_vcf,
    export_to_xlsx,
    export_variant_report_pdf,
)

DOWNLOADS_DIR = Path.home() / "Downloads"

from terminal_ui import (
    console,
    print_answer,
    print_banner,
    print_clear_notice,
    print_error,
    print_help,
    print_retry,
    print_setting_change,
    print_tool_call,
    print_tool_result,
)


MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

BUILD_LABELS = {
    "grch38": "GRCh38 (current, default)",
    "grch37": "GRCh37 (legacy)",
}

TRANSCRIPT_MODE_LABELS = {
    "mane_select": "MANE Select only",
    "all": "All transcripts",
}


def clean_user_path(path: str) -> str:
    return path.strip().strip("\"'")

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "When looking up genetic variants, use get_vep_consequence for supported HGVS inputs: "
        "genomic HGVS such as chr{N}:g...., or coding HGVS only when it includes a transcript "
        "accession such as NM_004333.6:c.1799T>A. Bare c. notation is ambiguous; ask for the "
        "transcript accession instead of guessing. If the user provides a well-known gene + protein change "
        "(e.g. 'BRAF V600E'), you may call get_clinvar_summary directly without needing "
        "get_vep_consequence first. For duplications, insertions, or frameshifts, only "
        "construct a genomic or transcript-qualified coding HGVS string if you are highly confident in the exact position. "
        "Prefer asking the user for the exact HGVS notation, such as from a lab report or "
        "ClinVar page, rather than guessing, since an incorrect coordinate can silently "
        "return data for the wrong variant. Do not use emojis, pictograms, or decorative "
        "symbols in your responses. Use plain text headings and concise Markdown tables."
    ),
}


def load_api_key() -> str | None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)
    return os.environ.get("OPENROUTER_API_KEY")


def openrouter_format_tools(mcp_tools: list[Any]) -> list[dict[str, Any]]:
    openrouter_tools = []
    for tool in mcp_tools:
        openrouter_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
        )
    return openrouter_tools


def openrouter_retry(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    api_key: str,
    max_retries: int = 3,
    backoff_seconds: int = 5,
) -> dict[str, Any]:
    response_json: dict[str, Any] = {}
    for attempt in range(1, max_retries + 1):
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": MODEL,
                "messages": messages,
                "tools": tools,
            },
            timeout=60,
        )
        response_json = response.json()

        if "error" not in response_json:
            return response_json

        if attempt < max_retries:
            print_retry(attempt, response_json["error"], backoff_seconds)
            time.sleep(backoff_seconds)

    raise RuntimeError(f"OpenRouter request failed after {max_retries} attempts: {response_json.get('error')}")


async def resolve_turn(
    client: Client,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    api_key: str,
    last_single_result: dict[str, Any],
) -> None:
    while True:
        with console.status("[tool]Thinking through the variant context..."):
            response_json = openrouter_retry(messages, tools, api_key)

        message = response_json["choices"][0]["message"]

        if not message.get("tool_calls"):
            messages.append(message)
            last_single_result["summary_text"] = message.get("content", "")
            print_answer(message.get("content", ""))
            return

        messages.append(message)

        for tool_call in message["tool_calls"]:
            name = tool_call["function"]["name"]
            try:
                args = json.loads(tool_call["function"]["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                print_error("Tool argument error", str(exc))
                raise

            print_tool_call(name, args)
            with console.status(f"[mcp]Running {name}..."):
                result = await client.call_tool(name=name, arguments=args)

            print_tool_result(name, result.data)

            if name == "get_vep_consequence":
                last_single_result["vep"] = result.data
            elif name == "get_clinvar_summary":
                last_single_result["clinvar"] = result.data

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result.data, default=str),
                }
            )


async def run_chat() -> None:
    api_key = load_api_key()
    if not api_key:
        print_error(
            "Missing OPENROUTER_API_KEY",
            "Add OPENROUTER_API_KEY to your .env file, then run vepclin again.",
        )
        return

    print_banner(MODEL, BUILD_LABELS[session_config.build], TRANSCRIPT_MODE_LABELS[session_config.transcript_mode])

    os.environ["VEPCLIN_EMBEDDED_CHAT"] = "1"
    async with Client(transport=mcp) as client:
        with console.status("[mcp]Loading MCP tools..."):
            mcp_tools = await client.list_tools()

        tools = openrouter_format_tools(mcp_tools)
        messages: list[dict[str, Any]] = [SYSTEM_MESSAGE.copy()]
        last_batch_results: list[dict] | None = None
        last_batch_path: str | None = None
        last_single_result: dict[str, Any] = {"vep": None, "clinvar": None, "summary_text": None}

        while True:
            user_query = Prompt.ask("[user]You[/]").strip()

            if not user_query:
                continue

            command = user_query.lower()
            if command in {"/exit", "/quit", "exit", "quit"}:
                console.print("[hint]Goodbye.[/]")
                return
            if command == "/help":
                print_help()
                continue
            if command == "/clear":
                messages = [SYSTEM_MESSAGE.copy()]
                print_clear_notice()
                continue
            if command == "/build":
                choice = await questionary.select(
                    "Select genome build:",
                    choices=[
                        questionary.Choice(BUILD_LABELS["grch38"], value="grch38"),
                        questionary.Choice(BUILD_LABELS["grch37"], value="grch37"),
                    ],
                    default=session_config.build,
                    show_selected=True,
                ).ask_async()
                if choice is not None:
                    session_config.build = choice
                    session_config.save()
                    print_setting_change(
                        "Genome Build Updated",
                        [
                            ("Build", BUILD_LABELS[choice]),
                            ("Applies to", "Future Ensembl VEP lookups in this chat"),
                            ("Saved to", session_config.config_path),
                        ],
                    )
                continue
            if command == "/batch":
                path = await questionary.path("Path to VCF file:").ask_async()
                if not path:
                    continue
                path = clean_user_path(path)
                last_batch_path = path

                try:
                    variants = variant_client_instance.parse_vcf(path)
                except FileNotFoundError:
                    print_error("File not found", f"No file at '{path}'.")
                    continue

                if not variants:
                    print_error("Empty batch", "No usable variant rows were found in that file.")
                    continue

                if len(variants) > session_config.MAX_BATCH_SIZE:
                    print_error(
                        "Batch too large",
                        f"{len(variants)} variants found; Ensembl's limit is "
                        f"{session_config.MAX_BATCH_SIZE} per request. Split the file and retry.",
                    )
                    continue

                with console.status(f"[mcp]Running {len(variants)} variants through VEP..."):
                    vep_results = variant_client_instance.get_vep_consequences_batch(
                        variants, build=session_config.build, transcript_mode=session_config.transcript_mode
                    )

                with console.status("[mcp]Checking ClinVar for each variant..."):
                    full_results = variant_client_instance.get_clinvar_summaries_batch(vep_results)
                    last_batch_results = full_results

                print_batch_results(full_results)
                continue

            if command == "/transcripts":
                choice = await questionary.select(
                    "Select transcript scope:",
                    choices=[
                        questionary.Choice("MANE Select only (recommended)", value="mane_select"),
                        questionary.Choice(TRANSCRIPT_MODE_LABELS["all"], value="all"),
                    ],
                    default=session_config.transcript_mode,
                    show_selected=True,
                ).ask_async()
                if choice is not None:
                    session_config.transcript_mode = choice
                    session_config.save()
                    print_setting_change(
                        "Transcript Scope Updated",
                        [
                            ("Scope", TRANSCRIPT_MODE_LABELS[choice]),
                            ("Applies to", "Future Ensembl VEP lookups in this chat"),
                            ("Saved to", session_config.config_path),
                        ],
                    )
                continue

            if command == "/report":
                vep = last_single_result.get("vep")
                clinvar = last_single_result.get("clinvar")
                if not vep and not clinvar:
                    print_error("Nothing to report", "Look up a variant in chat first, then run /report.")
                    continue

                gene = (vep or {}).get("gene_symbol") or "variant"
                protein = (vep or {}).get("protein_change_short") or "report"
                default_path = str(DOWNLOADS_DIR / f"{gene}_{protein}.pdf")

                out_path = await questionary.path(
                    "Save as (include filename):", default=default_path
                ).ask_async()
                if not out_path:
                    continue
                out_path = clean_user_path(out_path)

                try:
                    export_variant_report_pdf(
                        vep, clinvar, last_single_result.get("summary_text"), out_path
                    )
                    console.print(f"[hint]Saved to {out_path}[/]")
                except Exception as exc:
                    print_error("Export failed", str(exc))
                continue

            if command == "/export":
                if not last_batch_results:
                    print_error("Nothing to export", "Run /batch first, then /export.")
                    continue

                fmt = await questionary.select(
                    "Export format:",
                    choices=[
                        questionary.Choice("CSV (Comma-Separated Values)", value="csv"),
                        questionary.Choice("TSV (Tab-Separated Values)", value="tsv"),
                        questionary.Choice("VCF (Variant Call Format)", value="vcf"),
                        questionary.Choice("Excel (.xlsx, multi-sheet)", value="xlsx"),
                    ],
                ).ask_async()
                if fmt is None:
                    continue

                default_path = str(DOWNLOADS_DIR / f"batch_results.{fmt}")
                out_path = await questionary.path(
                    "Save as (include filename):", default=default_path
                ).ask_async()
                if not out_path:
                    continue
                out_path = clean_user_path(out_path)

                try:
                    if fmt == "csv":
                        export_to_csv(last_batch_results, out_path)
                        console.print(f"[hint]Saved to {out_path}[/]")
                    elif fmt == "tsv":
                        export_to_tsv(last_batch_results, out_path)
                        console.print(f"[hint]Saved to {out_path}[/]")
                    elif fmt == "xlsx":
                        export_to_xlsx(last_batch_results, out_path)
                        console.print(f"[hint]Saved to {out_path}[/]")
                    elif fmt == "vcf":
                        stats = export_annotated_vcf(last_batch_path, last_batch_results, out_path)
                        console.print(f"[hint]Saved to {out_path}[/]")
                        print_setting_change(
                            "Annotated VCF Export Summary",
                            [
                                ("Rows annotated", stats["annotated"]),
                                ("Rows with no matching result", stats["no_match"]),
                                ("Rows skipped (malformed)", stats["skipped"]),
                            ],
                        )
                except Exception as exc:
                    print_error("Export failed", str(exc))
                continue

            messages.append({"role": "user", "content": user_query})

            try:
                await resolve_turn(client, messages, tools, api_key, last_single_result)
            except httpx.HTTPError:
                print_error(
                    "Network error",
                    "Couldn't reach an upstream service. Check your connection and try again.",
                )
            except Exception as exc:
                print_error(
                    "Something went wrong",
                    "An unexpected error occurred. If this keeps happening, please report it.",
                )
                console.print(f"[hint](debug detail: {exc})[/]")


def main() -> None:
    asyncio.run(run_chat())


if __name__ == "__main__":
    main()