"""Agent orchestrator for EmberRoute.

Coordinates world-state tracking, change detection, tool execution loops with
deterministic fallback, and factual briefing generation guarded against hallucinations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.briefing import briefing_messages, build_facts, facts_hash, template_briefing
from core.agent.guard import verify
from core.agent.llm import LLMUnavailable, chat
from core.agent.tools import (
    TOOL_SCHEMAS,
    expand_search,
    get_fire_detections,
    get_settlement_detail,
    get_weather,
    run_full_plan,
    set_tool_context,
)
from core.agent.trace import Trace
from core.config import Settings, get_settings
from core.data.firms import fetch_detections
from core.data.weather import fetch_wind_series
from core.models import AOI, PipelineResult

logger = logging.getLogger(__name__)


def circular_diff_deg(a: float, b: float) -> float:
    """Compute shortest angular difference between two compass bearings in degrees [0, 180]."""
    diff = abs(a - b) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


@dataclass
class WorldState:
    """Current observational state of the monitored environment."""

    aoi: AOI
    mode: str = "LIVE"
    last_detection_hash: str = ""
    last_wind_summary: Dict[str, float] = field(default_factory=dict)
    last_result: Optional[PipelineResult] = None
    last_run_utc: Optional[datetime] = None
    degraded: Dict[str, bool] = field(default_factory=dict)
    override_hash: str = ""


@dataclass
class CycleResult:
    """Outcome of an orchestrated planning and briefing cycle."""

    result: Optional[PipelineResult]
    diff: Dict[str, Any]
    briefing: str
    trace: List[Dict[str, Any]]
    used_llm: bool = False
    provider: str = ""
    model: str = ""
    dropped_sentences: int = 0
    reasons: List[str] = field(default_factory=list)


@dataclass
class TickResult:
    """Result of an evaluation tick."""

    reasons: List[str]
    cycle_result: Optional[CycleResult] = None


def detect_change(prev: Optional[WorldState], cur: WorldState) -> List[str]:
    """Pure function evaluating environment differences between world states.

    Reasons:
    - NEW_DETECTIONS: satellite fire detection hash changed
    - WIND_DIR_SHIFT: circular wind direction changed by > 30 degrees
    - WIND_SPEED_CHANGE: wind speed changed relatively by > 25%
    - FEED_RECOVERED: a previously degraded feed returned to healthy status
    - MANUAL_REFRESH: explicit refresh or initial evaluation
    - OVERRIDE_CHANGED: scenario parameters or wind overrides modified
    """
    if prev is None:
        return ["MANUAL_REFRESH"]

    reasons: List[str] = []

    # 1. Detection differences
    if cur.last_detection_hash and cur.last_detection_hash != prev.last_detection_hash:
        reasons.append("NEW_DETECTIONS")

    # 2. Wind direction shift (> 30 degrees circular difference)
    prev_dir = prev.last_wind_summary.get("dir_from_deg")
    cur_dir = cur.last_wind_summary.get("dir_from_deg")
    if prev_dir is not None and cur_dir is not None:
        if circular_diff_deg(prev_dir, cur_dir) > 30.0:
            reasons.append("WIND_DIR_SHIFT")

    # 3. Wind speed change (> 25% relative difference)
    prev_spd = prev.last_wind_summary.get("speed_ms")
    cur_spd = cur.last_wind_summary.get("speed_ms")
    if prev_spd is not None and cur_spd is not None:
        base_spd = max(prev_spd, 0.5)
        if abs(cur_spd - prev_spd) / base_spd > 0.25:
            reasons.append("WIND_SPEED_CHANGE")

    # 4. Feed recovery
    for feed_name, was_degraded in prev.degraded.items():
        if was_degraded and not cur.degraded.get(feed_name, False):
            reasons.append("FEED_RECOVERED")
            break

    # 5. Overrides
    if cur.override_hash and cur.override_hash != prev.override_hash:
        reasons.append("OVERRIDE_CHANGED")

    return reasons


def diff(
    prev_result: Optional[PipelineResult],
    cur_result: Optional[PipelineResult],
) -> Dict[str, Any]:
    """Compute differential impact between successive simulation results."""
    if prev_result is None or cur_result is None:
        return {
            "status_changes": [],
            "depart_by_shifts": [],
            "new_trapped": [],
            "metric_deltas": {},
        }

    status_changes: List[Dict[str, Any]] = []
    depart_shifts: List[Dict[str, Any]] = []
    new_trapped: List[str] = []

    prev_plans = {p.settlement.name: p for p in prev_result.plans}
    prev_trapped = {p.settlement.name for p in prev_result.plans if p.status == "TRAPPED"}

    for cur_plan in cur_result.plans:
        name = cur_plan.settlement.name
        prev_p = prev_plans.get(name)

        if prev_p is not None:
            if cur_plan.status != prev_p.status:
                status_changes.append({
                    "settlement": name,
                    "from_status": prev_p.status,
                    "to_status": cur_plan.status,
                })
            if (
                cur_plan.depart_by_min is not None
                and prev_p.depart_by_min is not None
                and abs(cur_plan.depart_by_min - prev_p.depart_by_min) >= 10.0
            ):
                depart_shifts.append({
                    "settlement": name,
                    "from_depart_min": prev_p.depart_by_min,
                    "to_depart_min": cur_plan.depart_by_min,
                    "shift_min": cur_plan.depart_by_min - prev_p.depart_by_min,
                })

        if cur_plan.status == "TRAPPED" and name not in prev_trapped:
            new_trapped.append(name)

    metric_deltas: Dict[str, Any] = {}
    for k, cur_val in cur_result.metrics.items():
        prev_val = prev_result.metrics.get(k)
        if isinstance(cur_val, (int, float)) and isinstance(prev_val, (int, float)):
            metric_deltas[k] = cur_val - prev_val

    return {
        "status_changes": status_changes,
        "depart_by_shifts": depart_shifts,
        "new_trapped": new_trapped,
        "metric_deltas": metric_deltas,
    }


class Orchestrator:
    """Autonomous wildfire evacuation planning and monitoring orchestrator."""

    def __init__(
        self,
        aoi: Optional[AOI] = None,
        mode: str = "LIVE",
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        default_aoi = aoi or AOI(west=7.45, south=46.20, east=7.65, north=46.35)
        self.state = WorldState(aoi=default_aoi, mode=mode)
        self.last_briefing_hash: Optional[str] = None
        self.last_briefing_text: Optional[str] = None

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch tool invocation by name."""
        if name == "get_fire_detections":
            return get_fire_detections(args.get("aoi", {}))
        elif name == "get_weather":
            return get_weather(args.get("center", {}))
        elif name == "run_full_plan":
            return run_full_plan(
                aoi=args.get("aoi", {}),
                mode=args.get("mode", self.state.mode),
                ignition=args.get("ignition"),
                wind_override=args.get("wind_override"),
            )
        elif name == "get_settlement_detail":
            return get_settlement_detail(args.get("name", ""))
        elif name == "expand_search":
            return expand_search(
                aoi_scale=float(args.get("aoi_scale", 1.3)),
                horizon_min=int(args.get("horizon_min", 720)),
            )
        return {"error": "UNKNOWN_TOOL", "message": f"Tool '{name}' is not registered"}

    def run_deterministic_plan(
        self,
        aoi: AOI,
        mode: str,
        ignition: Optional[Dict[str, float]] = None,
        wind_override: Optional[Dict[str, float]] = None,
        trace: Optional[Trace] = None,
    ) -> Optional[PipelineResult]:
        """Fixed deterministic pipeline sequence when LLM planner is unavailable.

        Order: get_fire_detections -> get_weather -> run_full_plan
        Applies automatic recovery rules:
        - FEED_DOWN: retry 3 times with 1, 2, 4s backoff.
        - NO_FIRE: return None / signal NEEDS_SCENARIO (never invent an ignition).
        - zero threatened while detections exist: expand_search once.
        - OSM_EMPTY: shrink AOI to 70% once and retry.
        """
        aoi_dict = {"west": aoi.west, "south": aoi.south, "east": aoi.east, "north": aoi.north}
        center_dict = {"lat": aoi.center[0], "lon": aoi.center[1]}

        if trace:
            trace.append(
                step="planner_fallback",
                note="LLM unavailable, deterministic planner used",
                status="degraded",
            )

        # Step 1: Fire detections with backoff on FEED_DOWN
        for attempt in range(3):
            det_res = get_fire_detections(aoi_dict)
            if "error" not in det_res:
                break
            if det_res.get("error") == "FEED_DOWN" and attempt < 2:
                time.sleep(2**attempt)

        if mode == "LIVE" and det_res.get("summary", {}).get("count", 0) == 0:
            if trace:
                trace.append(
                    step="planner_halt",
                    note="NO_FIRE detected in LIVE mode; returning NEEDS_SCENARIO",
                    status="ok",
                )
            return None

        # Step 2: Weather with backoff
        for attempt in range(3):
            wea_res = get_weather(center_dict)
            if "error" not in wea_res:
                break
            if wea_res.get("error") == "FEED_DOWN" and attempt < 2:
                time.sleep(2**attempt)

        # Step 3: Run full plan
        plan_res = run_full_plan(
            aoi=aoi_dict,
            mode=mode,
            ignition=ignition,
            wind_override=wind_override,
        )

        # Recovery (d): OSM_EMPTY -> shrink AOI to 70% once and retry
        if plan_res.get("error") == "OSM_EMPTY":
            if trace:
                trace.append(step="recovery_osm_empty", note="Shrinking AOI to 70% and retrying", status="retry")
            c_lat, c_lon = aoi.center
            w_scaled = (aoi.east - aoi.west) * 0.7 / 2.0
            h_scaled = (aoi.north - aoi.south) * 0.7 / 2.0
            shrunk_aoi = {
                "west": c_lon - w_scaled,
                "south": c_lat - h_scaled,
                "east": c_lon + w_scaled,
                "north": c_lat + h_scaled,
            }
            plan_res = run_full_plan(aoi=shrunk_aoi, mode=mode, ignition=ignition, wind_override=wind_override)

        # Recovery (c): zero threatened settlements while detections exist -> expand_search once
        if (
            self.state.last_result
            and self.state.last_result.detections
            and self.state.last_result.metrics.get("n_threatened", 0) == 0
        ):
            if trace:
                trace.append(step="recovery_expand", note="Zero threatened settlements; expanding search once", status="retry")
            expand_search(aoi_scale=1.3)

        return self.state.last_result

    def run_cycle(
        self,
        reason: str = "MANUAL_REFRESH",
        ignition: Optional[Dict[str, float]] = None,
        wind_override: Optional[Dict[str, float]] = None,
    ) -> CycleResult:
        """Run a complete planning and briefing synthesis cycle."""
        trace = Trace()
        trace.append(step="cycle_start", note=f"Cycle triggered by {reason}", status="ok")

        prev_result = self.state.last_result
        cur_result: Optional[PipelineResult] = None
        used_llm_planner = False
        used_llm_briefing = False
        provider_used = ""
        model_used = ""
        dropped_sentences = 0

        with set_tool_context(self):
            # Attempt LLM Planning Loop
            system_prompt = (
                "You operate a wildfire evacuation planner. Never compute routes or fire arrival yourself; "
                "call tools. Default order: get_fire_detections, get_weather, run_full_plan. "
                "If a tool returns an error code, choose one recovery: retry once, expand_search, "
                "or stop and report. Never invent data. Reply DONE when finished."
            )
            aoi_dict = {
                "west": self.state.aoi.west,
                "south": self.state.aoi.south,
                "east": self.state.aoi.east,
                "north": self.state.aoi.north,
            }
            user_msg = (
                f"Reason: {reason}. AOI: {aoi_dict}. Mode: {self.state.mode}. "
                f"Ignition: {ignition}. WindOverride: {wind_override}."
            )
            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]

            tool_calls_count = 0
            executed_calls: Set[str] = set()

            try:
                while tool_calls_count < 5:
                    resp = chat(
                        messages=messages,
                        role="planner",
                        tools=TOOL_SCHEMAS,
                        max_tokens=150,
                        settings=self.settings,
                    )
                    provider_used = resp.provider
                    model_used = resp.model

                    if not resp.tool_calls:
                        # Model replied with text / finished
                        used_llm_planner = True
                        break

                    used_llm_planner = True
                    # Append assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": resp.text or "",
                        "tool_calls": resp.tool_calls,
                    })

                    all_succeeded = True
                    for tc in resp.tool_calls:
                        tool_calls_count += 1
                        fn_name = tc.get("function", {}).get("name", "")
                        raw_args = tc.get("function", {}).get("arguments", "{}")

                        # Guard against repeated or unbounded calls
                        call_sig = f"{fn_name}:{raw_args}"
                        if call_sig in executed_calls:
                            logger.warning("Repeated tool call detected: %s; falling back to deterministic planner", call_sig)
                            raise ValueError(f"Repeated tool call: {call_sig}")
                        executed_calls.add(call_sig)

                        try:
                            parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except Exception:
                            parsed_args = {}

                        with trace.step(f"tool_{fn_name}", tool=fn_name, args_summary=str(parsed_args)[:60]):
                            tool_out = self._execute_tool(fn_name, parsed_args)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", f"call_{tool_calls_count}"),
                            "content": json.dumps(tool_out),
                        })

                        if "error" in tool_out:
                            all_succeeded = False

                    if tool_calls_count >= 5:
                        logger.info("Reached maximum tool call limit of 5")
                        break

                cur_result = self.state.last_result

            except (LLMUnavailable, Exception) as exc:
                logger.info("Falling back to deterministic planner: %s", exc)
                cur_result = self.run_deterministic_plan(
                    aoi=self.state.aoi,
                    mode=self.state.mode,
                    ignition=ignition,
                    wind_override=wind_override,
                    trace=trace,
                )

        # Differential evaluation
        diff_data = diff(prev_result, cur_result)

        # Briefing Generation
        briefing_text = ""
        if cur_result is not None:
            facts = build_facts(cur_result, diff_data)
            f_hash = facts_hash(facts)

            # Re-use cached briefing if facts are strictly identical
            if self.last_briefing_hash == f_hash and self.last_briefing_text:
                briefing_text = self.last_briefing_text
                trace.append(step="briefing_cached", note="Re-using cached briefing for identical facts", status="ok")
            else:
                try:
                    b_messages = briefing_messages(facts)
                    b_resp = chat(
                        messages=b_messages,
                        role="briefing",
                        max_tokens=350,
                        settings=self.settings,
                    )
                    provider_used = b_resp.provider or provider_used
                    model_used = b_resp.model or model_used

                    # Verify through strict hallucination guard
                    guard_res = verify(b_resp.text or "", facts)
                    if guard_res.ok:
                        briefing_text = guard_res.clean_text
                        dropped_sentences = guard_res.dropped_count
                        used_llm_briefing = True
                        self.last_briefing_hash = f_hash
                        self.last_briefing_text = briefing_text
                        trace.append(step="briefing_generated", note=f"LLM briefing verified ({dropped_sentences} dropped)", status="ok")
                    else:
                        logger.warning("Guard verification failed (ok=False); using template fallback")
                        briefing_text = template_briefing(facts)
                        dropped_sentences = guard_res.dropped_count
                        trace.append(step="briefing_guard_fallback", note="Guard verification failed; template used", status="degraded")
                except (LLMUnavailable, Exception) as b_exc:
                    logger.info("Briefing LLM unavailable (%s); using template briefing", b_exc)
                    briefing_text = template_briefing(facts)
                    trace.append(step="briefing_fallback", note="LLM unavailable; template used", status="degraded")
        else:
            briefing_text = "No active fire detections in Area of Interest. Switch to SCENARIO mode to run simulation."
            trace.append(step="briefing_no_fire", note="Zero fire detections", status="ok")

        self.state.last_result = cur_result
        self.state.last_run_utc = datetime.now(timezone.utc)

        trace.append(step="cycle_complete", note="Orchestration cycle completed", status="ok")

        return CycleResult(
            result=cur_result,
            diff=diff_data,
            briefing=briefing_text,
            trace=trace.to_list(),
            used_llm=used_llm_briefing,
            provider=provider_used,
            model=model_used,
            dropped_sentences=dropped_sentences,
            reasons=[reason],
        )

    def tick(self) -> TickResult:
        """Execute a single polling tick without invoking the LLM if no changes occur."""
        # 1. Fetch current live feed summaries without LLM
        curr_det_hash = ""
        degraded: Dict[str, bool] = {}

        if self.state.mode == "LIVE":
            try:
                dets, prov = fetch_detections(self.state.aoi, hours=24)
                det_bytes = json.dumps([{"lat": d.lat, "lon": d.lon, "frp": d.frp} for d in dets], sort_keys=True)
                curr_det_hash = hashlib.sha256(det_bytes.encode()).hexdigest()
                degraded["firms"] = prov.is_stale
            except Exception:
                degraded["firms"] = True

        wind_summary: Dict[str, float] = {}
        try:
            c_lat, c_lon = self.state.aoi.center
            wind, prov = fetch_wind_series(c_lat, c_lon)
            wind_summary = {
                "speed_ms": wind.speed_ms[0] if wind.speed_ms else 0.0,
                "dir_from_deg": wind.dir_from_deg[0] if wind.dir_from_deg else 0.0,
            }
            degraded["weather"] = wind.is_stale
        except Exception:
            degraded["weather"] = True

        cur_world = WorldState(
            aoi=self.state.aoi,
            mode=self.state.mode,
            last_detection_hash=curr_det_hash,
            last_wind_summary=wind_summary,
            degraded=degraded,
        )

        reasons = detect_change(self.state if self.state.last_run_utc else None, cur_world)

        if not reasons:
            return TickResult(reasons=[])

        # Execute cycle on detected reasons
        cycle_res = self.run_cycle(reason=reasons[0])
        self.state.last_detection_hash = curr_det_hash
        self.state.last_wind_summary = wind_summary
        self.state.degraded = degraded

        return TickResult(reasons=reasons, cycle_result=cycle_res)
