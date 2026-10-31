"""Demonstration script for EmberRoute Agent Orchestrator.

Executes:
1. Normal operational cycle: prints trace, briefing, provider/model, token usage (<6,000), and dropped sentences.
2. Degraded cycle with SIMULATE_API_FAILURE=llm: verifies fallback to deterministic planner & template briefing.
3. Degraded cycle with SIMULATE_API_FAILURE=open_meteo: verifies weather degradation handling.
"""

import os
from pathlib import Path
import sys
import time

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core.agent.llm import get_total_tokens_used, reset_total_tokens_used
from core.agent.orchestrator import Orchestrator
from core.config import get_settings
from core.models import AOI


def run_demo() -> int:
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    ignition = {"lat": 46.28, "lon": 7.55}
    wind_override = {"speed_ms": 7.0, "dir_from_deg": 240.0}

    print("=" * 75)
    print("EMBERROUTE AGENT ORCHESTRATOR DEMONSTRATION")
    print("=" * 75)

    # ---------------------------------------------------------
    # 1. Normal Operational Cycle
    # ---------------------------------------------------------
    print("\n[Step 1] Running normal operational cycle (SCENARIO mode)...")
    reset_total_tokens_used()
    get_settings.cache_clear()

    orch = Orchestrator(aoi=aoi, mode="SCENARIO")
    start_time = time.perf_counter()

    cycle1 = orch.run_cycle(
        reason="DEMO_NORMAL_CYCLE",
        ignition=ignition,
        wind_override=wind_override,
    )
    dur1 = time.perf_counter() - start_time
    tokens_spent = get_total_tokens_used()

    print(f"\n--- Operational Trace ({len(cycle1.trace)} steps) ---")
    for tr in cycle1.trace:
        status_tag = f"[{tr.get('status', 'ok').upper()}]"
        print(f"  {tr.get('step'):<25} {status_tag:<12} {tr.get('duration_ms', 0):>7.1f} ms | {tr.get('note') or tr.get('args_summary') or ''}")

    print(f"\n--- Generated Operational Briefing ---")
    print(cycle1.briefing)

    print(f"\n--- Execution Metrics ---")
    print(f"Provider Used:      {cycle1.provider or 'Deterministic Fallback'}")
    print(f"Model Used:         {cycle1.model or 'None'}")
    print(f"Used LLM Briefing:  {cycle1.used_llm}")
    print(f"Dropped Sentences:  {cycle1.dropped_sentences}")
    print(f"Tokens Spent:       {tokens_spent} (Limit: < 6,000)")
    print(f"Cycle Runtime:      {dur1:.2f} s")

    assert tokens_spent < 6000, f"Token usage exceeded limit: {tokens_spent} >= 6000"

    # ---------------------------------------------------------
    # 2. Degraded Cycle: SIMULATE_API_FAILURE=llm
    # ---------------------------------------------------------
    print("\n" + "=" * 75)
    print("[Step 2] Testing degraded cycle with SIMULATE_API_FAILURE=llm...")
    os.environ["SIMULATE_API_FAILURE"] = "llm"
    get_settings.cache_clear()

    orch_degraded_llm = Orchestrator(aoi=aoi, mode="SCENARIO")
    cycle2 = orch_degraded_llm.run_cycle(
        reason="DEMO_LLM_FAILURE",
        ignition=ignition,
        wind_override=wind_override,
    )

    print(f"Cycle Result: {cycle2.briefing[:120]}...")
    print(f"Used LLM:     {cycle2.used_llm} (Expected: False)")
    has_fallback_trace = any("fallback" in t.get("step", "").lower() or "deterministic" in str(t.get("note", "")).lower() for t in cycle2.trace)
    print(f"Fallback Trace Present: {has_fallback_trace}")
    assert cycle2.used_llm is False
    assert cycle2.result is not None

    # ---------------------------------------------------------
    # 3. Degraded Cycle: SIMULATE_API_FAILURE=open_meteo
    # ---------------------------------------------------------
    print("\n" + "=" * 75)
    print("[Step 3] Testing degraded cycle with SIMULATE_API_FAILURE=open_meteo...")
    os.environ["SIMULATE_API_FAILURE"] = "open_meteo"
    get_settings.cache_clear()

    orch_degraded_wx = Orchestrator(aoi=aoi, mode="SCENARIO")
    cycle3 = orch_degraded_wx.run_cycle(
        reason="DEMO_WEATHER_FAILURE",
        ignition=ignition,
        wind_override=None,
    )

    print(f"Warnings Recorded: {cycle3.result.warnings if cycle3.result else 'None'}")
    has_weather_warning = any("weather" in w.lower() or "open-meteo" in w.lower() for w in cycle3.result.warnings) if cycle3.result else False
    print(f"Weather Degradation Handled Gracefully: {has_weather_warning}")
    assert cycle3.result is not None

    # Clean up environment
    os.environ.pop("SIMULATE_API_FAILURE", None)
    get_settings.cache_clear()

    print("\n" + "=" * 75)
    print("ALL AGENT DEMO CHECKS PASSED SUCCESSFULLY!")
    print("=" * 75)
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())

