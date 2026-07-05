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

from mcp_server import mcp
from terminal_ui import (
    console,
    print_answer,
    print_banner,
    print_clear_notice,
    print_error,
    print_help,
    print_retry,
    print_tool_call,
    print_tool_result,
)


MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "When looking up genetic variants, prefer genomic HGVS notation (chr{N}:g....) "
        "for get_vep_consequence. If the user provides a well-known gene + protein change "
        "(e.g. 'BRAF V600E'), you may call get_clinvar_summary directly without needing "
        "get_vep_consequence first. For duplications, insertions, or frameshifts, only "
        "construct a genomic coordinate if you are highly confident in the exact position. "
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
) -> None:
    while True:
        with console.status("[tool]Thinking through the variant context..."):
            response_json = openrouter_retry(messages, tools, api_key)

        message = response_json["choices"][0]["message"]

        if not message.get("tool_calls"):
            messages.append(message)
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

    print_banner()

    os.environ["VEPCLIN_EMBEDDED_CHAT"] = "1"
    async with Client(transport=mcp) as client:
        with console.status("[mcp]Loading MCP tools..."):
            mcp_tools = await client.list_tools()

        tools = openrouter_format_tools(mcp_tools)
        messages: list[dict[str, Any]] = [SYSTEM_MESSAGE.copy()]

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

            messages.append({"role": "user", "content": user_query})

            try:
                await resolve_turn(client, messages, tools, api_key)
            except Exception as exc:
                print_error("Conversation error", str(exc))


def main() -> None:
    asyncio.run(run_chat())


if __name__ == "__main__":
    main()
