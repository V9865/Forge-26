"""Self-test script for EmberRoute LLM chain entries.

For each configured provider:model in LLM_CHAIN:
1. Runs a one-line plain text completion.
2. Runs a tiny function-calling verification with a get_time tool.
3. Prints provider, model, latency, token usage, and tool validity.
4. Checks local Ollama connectivity and prints model list or setup instructions.
Exits 0 if at least one entry passes; otherwise exits non-zero.
"""

from pathlib import Path
import sys
import time
from typing import Any, Dict, List
import httpx
import openai
from openai import OpenAI

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core.agent.llm import parse_provider_spec
from core.config import get_settings


def main() -> int:
    settings = get_settings()
    chain_str = settings.LLM_CHAIN.strip()

    print("=" * 75)
    print("EMBERROUTE LLM CHAIN SELF-TEST")
    print("=" * 75)
    print(f"Configured LLM_CHAIN: {chain_str}")
    print(f"Groq API Key Configured: {'YES' if settings.GROQ_API_KEY.strip() else 'NO'}")
    print(f"Groq Base URL: {settings.GROQ_BASE_URL}")
    print(f"Ollama Base URL: {settings.OLLAMA_BASE_URL}\n")

    time_tool: List[Dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Get current UTC time",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
    ]

    specs = [parse_provider_spec(item) for item in chain_str.split(",") if item.strip()]
    passed_count = 0
    results_table = []

    for spec in specs:
        if not spec:
            continue

        prov = spec.provider
        model = spec.model
        print(f"Testing [{prov}] -> {model}...")

        # Build client
        try:
            if prov == "groq":
                key = settings.GROQ_API_KEY.strip()
                if not key:
                    results_table.append((prov, model, "SKIP", "0 ms", 0, "No GROQ_API_KEY set"))
                    print(f"  Skipping Groq: GROQ_API_KEY is not set.\n")
                    continue
                client = OpenAI(
                    base_url=settings.GROQ_BASE_URL.rstrip("/"),
                    api_key=key,
                    timeout=float(settings.LLM_TIMEOUT_S),
                )
            elif prov == "ollama":
                base_url = settings.OLLAMA_BASE_URL.rstrip("/")
                if not base_url.endswith("/v1"):
                    base_url = f"{base_url}/v1"
                client = OpenAI(
                    base_url=base_url,
                    api_key="ollama",
                    timeout=float(settings.LLM_TIMEOUT_S),
                )
            else:
                results_table.append((prov, model, "FAIL", "0 ms", 0, f"Unsupported provider {prov}"))
                print(f"  Unsupported provider: {prov}\n")
                continue

            # 1. Plain text completion
            t0 = time.perf_counter()
            resp1 = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with only the word OK."}],
                max_tokens=20,
                temperature=0.0,
            )
            lat1_ms = (time.perf_counter() - t0) * 1000.0
            tokens1 = resp1.usage.total_tokens if resp1.usage else 0

            # 2. Tool calling test
            t1 = time.perf_counter()
            resp2 = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "What is the current time? Call the get_time tool."}],
                tools=time_tool,
                tool_choice="auto",
                max_tokens=60,
                temperature=0.0,
            )
            lat2_ms = (time.perf_counter() - t1) * 1000.0
            tokens2 = resp2.usage.total_tokens if resp2.usage else 0

            tool_called = False
            msg2 = resp2.choices[0].message
            if msg2.tool_calls:
                for tc in msg2.tool_calls:
                    if tc.function.name == "get_time":
                        tool_called = True
                        break

            tot_lat_ms = lat1_ms + lat2_ms
            tot_tokens = tokens1 + tokens2
            tool_status = "Well-Formed Tool Call" if tool_called else "No Tool Call Emitted"

            print(f"  Completion: '{resp1.choices[0].message.content.strip()}' in {lat1_ms:.1f}ms")
            print(f"  Tool-call test: {tool_status} in {lat2_ms:.1f}ms")
            print(f"  Total tokens: {tot_tokens}\n")

            results_table.append((prov, model, "PASS", f"{tot_lat_ms:.1f} ms", tot_tokens, tool_status))
            passed_count += 1

        except Exception as exc:
            print(f"  Error testing {prov}:{model}: {exc}\n")
            results_table.append((prov, model, "FAIL", "ERR", 0, str(exc)[:35]))

    # Check local Ollama status
    print("-" * 75)
    print("LOCAL OLLAMA DIAGNOSTICS")
    print("-" * 75)
    ollama_root = settings.OLLAMA_BASE_URL.rstrip("/")
    if ollama_root.endswith("/v1"):
        ollama_root = ollama_root[:-3]

    try:
        ollama_resp = httpx.get(f"{ollama_root}/api/tags", timeout=1.5)
        if ollama_resp.status_code == 200:
            models = [m.get("name") for m in ollama_resp.json().get("models", [])]
            print(f"Ollama server running at {ollama_root}")
            print(f"Installed models: {', '.join(models) if models else 'None'}")
        else:
            print(f"Ollama server returned HTTP {ollama_resp.status_code}")
    except Exception:
        print(f"Local Ollama is not running at {ollama_root} (optional local backup)")

    print("\nTo setup local Ollama backup models, run:")
    print("  ollama pull qwen2.5:7b-instruct")
    print("  ollama pull llama3.1:8b\n")

    # Summary table
    print("=" * 75)
    print(f"{'Provider':<10} {'Model':<30} {'Status':<8} {'Latency':<12} {'Tokens':<8} {'Detail'}")
    print("-" * 75)
    for p, m, s, lat, tok, det in results_table:
        print(f"{p:<10} {m:<30} {s:<8} {lat:<12} {tok:<8} {det}")
    print("=" * 75)

    if passed_count > 0:
        print(f"RESULT: PASS ({passed_count} provider(s) operational)\n")
        return 0
    else:
        print("RESULT: FAIL (No configured LLM providers operational)\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

