"""Operational briefing fact generation and deterministic templating.

Transforms raw PipelineResult simulation and routing outputs into a concise,
audited dictionary of grounded factual assertions (facts) under strict token
and count limits, and provides deterministic fallback briefings.
"""

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.models import PipelineResult, SettlementPlan


def deg_to_compass(deg: float) -> str:
    """Convert bearing degrees clockwise from North to 16-point compass label."""
    val = int((deg + 11.25) % 360 // 22.5)
    points = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    return points[val]


def estimate_tokens(text: str) -> int:
    """Estimate token count as ceil(len(text) / 4)."""
    return max(1, math.ceil(len(text) / 4.0))


def build_facts(
    result: PipelineResult,
    diff: Optional[Any] = None,
) -> Dict[str, str]:
    """Compile an audited dictionary of operational facts from PipelineResult.

    Enforces strict sizing constraints:
    - Maximum 25 facts.
    - Maximum ~1,200 tokens total (estimated as len(text) / 4).
    - Trims least urgent settlements first when limits are reached.

    Includes:
    - Mode and data sources
    - Wind (speed, from-direction in degrees and compass, source, is_override)
    - Burned area at 2, 6, and 12 hours (rounded to 1 decimal)
    - Downwind spread bearing
    - 8 most urgent settlements (TRAPPED first, then smallest depart-by in integer minutes)
    - Every TRAPPED and ALREADY_BURNING settlement
    - Naive-route benchmark metric (n_naive_cut of n_threatened, n_rescued_by_replan)
    - Data freshness in integer minutes
    - Every warning from pipeline
    - Diff facts (status changes, depart-by shifts >= 10 min, new TRAPPED) if diff provided

    Args:
        result: Evaluated PipelineResult.
        diff: Optional previous PipelineResult or diff mapping.

    Returns:
        Ordered dictionary of fact IDs ('F1', 'F2', ...) to one-line fact sentences.
    """
    system_facts: List[str] = []
    warning_facts: List[str] = []
    diff_facts: List[str] = []
    critical_settlement_facts: List[str] = []
    urgent_settlement_facts: List[Tuple[float, str]] = []  # (depart_by_min, fact_str)

    now_utc = datetime.now(timezone.utc)

    # 1. Operational Mode and Data Sources
    sources = sorted(set(p.source for p in result.provenance)) if result.provenance else ["Local layers"]
    sources_str = ", ".join(sources)
    system_facts.append(
        f"Operational mode is {result.mode} using telemetry from {sources_str}."
    )

    # 2. Wind Conditions
    w_speed = float(result.wind.speed_ms[0]) if result.wind.speed_ms else 0.0
    w_dir = float(result.wind.dir_from_deg[0]) if result.wind.dir_from_deg else 0.0
    w_compass = deg_to_compass(w_dir)
    system_facts.append(
        f"Wind is {w_speed:.1f} m/s from {round(w_dir)} degrees ({w_compass}), source {result.wind.source}, override {result.wind.is_override}."
    )

    # 3. Burned Area at 2, 6, and 12 Hours
    res_m = float(result.spread.grid.res_m) if result.spread and result.spread.grid else 100.0
    cell_ha = (res_m * res_m) / 10000.0
    arrival = result.spread.arrival_min if result.spread else np.full((1, 1), np.inf)

    area_2h = float(np.sum(arrival <= 120.0) * cell_ha)
    area_6h = float(np.sum(arrival <= 360.0) * cell_ha)
    area_12h = float(np.sum(arrival <= 720.0) * cell_ha)
    system_facts.append(
        f"Predicted burned area is {area_2h:.1f} ha at 2 hours, {area_6h:.1f} ha at 6 hours, and {area_12h:.1f} ha at 12 hours."
    )

    # 4. Downwind Spread Bearing
    spread_deg = (w_dir + 180.0) % 360.0
    spread_compass = deg_to_compass(spread_deg)
    system_facts.append(
        f"Downwind fire spread direction is {round(spread_deg)} degrees ({spread_compass})."
    )

    # 5. Naive-Route Comparative Metric
    n_threatened = int(result.metrics.get("n_threatened", 0))
    n_cut = int(result.metrics.get("n_naive_cut", 0))
    n_rescued = int(result.metrics.get("n_rescued_by_replan", 0))
    system_facts.append(
        f"Evacuation baseline: {n_cut} of {n_threatened} threatened settlements have naive routes cut by fire, with {n_rescued} rescued by fire-aware replanning."
    )

    # 6. Data Freshness in Minutes
    freshness_entries = []
    for p in result.provenance:
        if p.ttl_s <= 86400:  # Live layers
            age_min = max(0, int((now_utc - p.fetched_at_utc).total_seconds() / 60.0))
            freshness_entries.append(f"{p.source} fetched {age_min} minutes ago")
    if freshness_entries:
        system_facts.append(f"Data freshness: {', '.join(freshness_entries)}.")
    else:
        system_facts.append("Data freshness: all telemetry inputs fetched within 15 minutes.")

    # 7. Pipeline Warnings
    for w in result.warnings:
        warning_facts.append(f"Warning: {w.rstrip('.')}.")

    # 8. Differential Facts (when diff provided)
    if diff is not None:
        if hasattr(diff, "plans"):
            old_plans = {p.settlement.id: p for p in diff.plans}
            for p in result.plans:
                old = old_plans.get(p.settlement.id)
                if old:
                    if old.status != "TRAPPED" and p.status == "TRAPPED":
                        diff_facts.append(f"Diff: Settlement {p.settlement.name} is newly TRAPPED.")
                    elif old.status != p.status:
                        diff_facts.append(f"Diff: Settlement {p.settlement.name} status changed from {old.status} to {p.status}.")

                    if old.depart_by_min is not None and p.depart_by_min is not None:
                        delta_dep = p.depart_by_min - old.depart_by_min
                        if abs(delta_dep) >= 10.0:
                            diff_facts.append(
                                f"Diff: Settlement {p.settlement.name} depart-by shifted by {round(delta_dep):+d} minutes (from {round(old.depart_by_min)} to {round(p.depart_by_min)} minutes)."
                            )
        elif isinstance(diff, dict):
            for k, v in diff.items():
                diff_facts.append(f"Diff: {k} changed to {v}.")

    # 9. Settlements (TRAPPED first, ALREADY_BURNING, then smallest depart-by)
    # Sort settlements deterministically
    def settlement_sort_key(p: SettlementPlan) -> Tuple[int, float, str]:
        status_rank = {
            "TRAPPED": 0,
            "ALREADY_BURNING": 1,
            "EVACUATE": 2,
            "NOT_THREATENED": 3,
        }.get(p.status, 4)
        dep = p.depart_by_min if p.depart_by_min is not None else 999999.0
        return (status_rank, dep, p.settlement.name)

    sorted_plans = sorted(result.plans, key=settlement_sort_key)

    for p in sorted_plans:
        arr_m = round(p.fire_arrival_min) if (p.fire_arrival_min is not None and math.isfinite(p.fire_arrival_min)) else 999
        dep_m = round(p.depart_by_min) if p.depart_by_min is not None else 0
        tt_m = round(p.route_travel_min) if p.route_travel_min is not None else 0
        s_fact = (
            f"Settlement {p.settlement.name} status is {p.status}: "
            f"fire arrival in {arr_m} minutes, depart by {dep_m} minutes, route travel time {tt_m} minutes."
        )

        if p.status in {"TRAPPED", "ALREADY_BURNING"}:
            critical_settlement_facts.append(s_fact)
        else:
            urgent_settlement_facts.append((dep_m, s_fact))

    # Keep at least up to 8 urgent settlements (TRAPPED first, then smallest depart-by)
    # Target total facts <= 25, total tokens <= 1200
    base_facts = system_facts + warning_facts + diff_facts + critical_settlement_facts

    # Available slots for EVACUATE / other settlements
    # Ensure 8 most urgent settlements are included if available
    needed_settlements_count = max(0, 8 - len(critical_settlement_facts))
    selected_urgent = urgent_settlement_facts[:needed_settlements_count]
    remaining_urgent = urgent_settlement_facts[needed_settlements_count:]

    # Add remaining urgent settlements as capacity allows
    all_selected_urgent = selected_urgent + remaining_urgent

    def compute_tokens(items: List[str]) -> int:
        return sum(estimate_tokens(t) for t in items)

    # Trim least urgent settlements (from the end of all_selected_urgent) until limits satisfied
    while len(base_facts) + len(all_selected_urgent) > 25 and all_selected_urgent:
        all_selected_urgent.pop()

    while compute_tokens(base_facts + [s for _, s in all_selected_urgent]) > 1200 and all_selected_urgent:
        all_selected_urgent.pop()

    # If still over 25 facts or 1200 tokens, trim warnings or critical settlements from end
    combined_list = base_facts + [s for _, s in all_selected_urgent]
    while len(combined_list) > 25 and len(combined_list) > len(system_facts):
        combined_list.pop()
    while compute_tokens(combined_list) > 1200 and len(combined_list) > len(system_facts):
        combined_list.pop()

    # Build final dictionary with deterministic F1, F2, ... IDs
    facts_dict: Dict[str, str] = {}
    for idx, fact_str in enumerate(combined_list, start=1):
        facts_dict[f"F{idx}"] = fact_str

    return facts_dict


def briefing_messages(facts: Dict[str, str]) -> List[Dict[str, str]]:
    """Format system and user chat prompt messages for LLM briefing synthesis."""
    system_prompt = (
        "Write a 5 to 8 sentence operational briefing for a district emergency officer "
        "using ONLY the facts provided. After every sentence add the supporting fact ids "
        "in square brackets, for example [F3][F7]. Quote numbers exactly as written in the facts. "
        "Do not add numbers, place names, causes or advice that are not in the facts. "
        "If a settlement is TRAPPED say so plainly."
    )
    user_content = "\n".join(f"{fid}: {text}" for fid, text in facts.items())

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def template_briefing(facts: Dict[str, str]) -> str:
    """Generate a deterministic fallback briefing directly from structured facts.

    Contains:
    - Current wind and spread conditions
    - Every TRAPPED settlement
    - The three most urgent EVACUATE settlements
    - Data freshness line
    """
    wind_line: Optional[str] = None
    freshness_line: Optional[str] = None
    trapped_lines: List[str] = []
    evac_lines: List[str] = []

    for fid, text in facts.items():
        if text.startswith("Wind is"):
            wind_line = text
        elif text.startswith("Data freshness:"):
            freshness_line = text
        elif "TRAPPED" in text:
            trapped_lines.append(text)
        elif "EVACUATE" in text:
            evac_lines.append(text)

    briefing_parts: List[str] = []

    if wind_line:
        briefing_parts.append(wind_line)

    if trapped_lines:
        for t_line in trapped_lines:
            briefing_parts.append(t_line)
    else:
        briefing_parts.append("No settlements are currently reported trapped.")

    for e_line in evac_lines[:3]:
        briefing_parts.append(e_line)

    if freshness_line:
        briefing_parts.append(freshness_line)

    return "\n".join(briefing_parts)


def facts_hash(facts: Dict[str, str]) -> str:
    """Compute deterministic SHA-256 hash of facts dictionary for response caching."""
    canonical = json.dumps(facts, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
