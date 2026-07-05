from dotenv import load_dotenv
from pathlib import Path
import httpx
import os
import time

import asyncio
from fastmcp.client import Client
from mcp_server import mcp
import json

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
api_key = os.environ.get("OPENROUTER_API_KEY")

def openrouter_format_tools(mcp_tools):
    openrouter_tools = []
    for tool in mcp_tools:
        openrouter_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
        })
    return openrouter_tools

def openrouter_retry(messages, tools, max_retries=3, backoff_seconds=5):
    for attempt in range(1, max_retries + 1):
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                "messages": messages,
                "tools": tools,
            },
        )
        response_json = response.json()

        if "error" not in response_json:
            return response_json  # success

        print(f"Attempt {attempt} failed: {response_json['error']}")

        if attempt < max_retries:
            print(f"Retrying in {backoff_seconds} seconds...")
            time.sleep(backoff_seconds)

    raise RuntimeError(f"OpenRouter request failed after {max_retries} attempts: {response_json['error']}")

async def run_query(question: str):
    async with Client(transport=mcp) as client:
        tools = await client.list_tools()
        openrouter_tools = openrouter_format_tools(tools)

        messages = [{"role": "user", "content": question}]
        while True:
            response_json = openrouter_retry(messages, openrouter_tools)
            message = response_json["choices"][0]["message"]

            if not message.get("tool_calls"):
                print("FINAL ANSWER:", message["content"])
                return

            messages.append(message)

            for tool_call in message["tool_calls"]:
                name = tool_call["function"]["name"]
                args = json.loads(tool_call["function"]["arguments"])
                print(f"Calling tool: {name} with {args}")

                result = await client.call_tool(name=name, arguments=args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result.data),
                })

user_query = input("What genomic variant do you have a question about?: ")
asyncio.run(run_query("What does the variant chr7:g.140753336A>T do, and is it dangerous?"))