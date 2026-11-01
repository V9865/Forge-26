"""Asynchronous Job Manager for EmberRoute simulation jobs.

Executes heavy simulation pipelines in a bounded ThreadPoolExecutor(max_workers=2)
with identical input caching within 60s, job expiry after 30 minutes,
and live stage/progress tracking.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from api.geojson import (
    build_arrival_bands_geojson,
    build_detections_geojson,
    build_naive_cut_segments_geojson,
    build_routes_geojson,
    build_settlements_geojson,
    build_roads_geojson,
)
from api.schemas import (
    AOIModel,
    BriefingModel,
    ErrorDetail,
    GridModel,
    JobStatus,
    PlanRequest,
    PlanResult,
    ProvenanceModel,
    TraceStepModel,
    WindModel,
    WindNowModel,
    WindPointModel,
)
from core.agent.briefing import build_facts, template_briefing
from core.agent.guard import verify
from core.agent.llm import LLMUnavailable, chat
from core.errors import FeedError
from core.models import AOI, PipelineResult
from core.pipeline import NoActiveFireError, PipelineError, run_pipeline

logger = logging.getLogger(__name__)

# Stages and proportional progress weights
STAGE_PROGRESS_MAP: Dict[str, float] = {
    "init": 0.05,
    "input_validation": 0.10,
    "fetch_detections": 0.25,
    "fetch_weather": 0.35,
    "build_layers": 0.50,
    "run_spread": 0.70,
    "fetch_osm": 0.80,
    "evacuation_planning": 0.90,
    "briefing_synthesis": 0.95,
    "done": 1.00,
}


def compute_request_hash(req: PlanRequest) -> str:
    """Deterministic hash of simulation parameters for 60-second result caching."""
    payload = {
        "west": round(req.aoi.west, 4),
        "south": round(req.aoi.south, 4),
        "east": round(req.aoi.east, 4),
        "north": round(req.aoi.north, 4),
        "mode": req.mode,
        "ignition": {"lat": round(req.ignition.lat, 4), "lon": round(req.ignition.lon, 4)} if req.ignition else None,
        "wind_override": (
            {"speed_ms": req.wind_override.speed_ms, "dir_from_deg": req.wind_override.dir_from_deg}
            if req.wind_override
            else None
        ),
        "resolution_m": req.resolution_m,
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class JobRecord:
    """Internal state tracking a simulation job."""

    job_id: str
    input_hash: str
    request: PlanRequest
    created_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: JobStatus = "queued"
    stage: str = "Job queued"
    progress: float = 0.0
    trace: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[PlanResult] = None
    error: Optional[ErrorDetail] = None


class JobManager:
    """Thread-safe background job manager."""

    def __init__(self, max_workers: int = 2) -> None:
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.jobs: Dict[str, JobRecord] = {}
        self.hash_to_job: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._execution_semaphore = threading.Semaphore(max_workers)

    def _cleanup_expired_jobs(self) -> None:
        """Purge jobs older than 30 minutes."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=30)
        expired_ids = [jid for jid, j in self.jobs.items() if j.created_at_utc < cutoff]
        for jid in expired_ids:
            rec = self.jobs.pop(jid, None)
            if rec and rec.input_hash in self.hash_to_job:
                if self.hash_to_job[rec.input_hash] == jid:
                    del self.hash_to_job[rec.input_hash]

    def submit(self, request: PlanRequest) -> str:
        """Submit a new simulation request.

        Returns an existing job ID if identical request was received within 60s.
        """
        with self._lock:
            self._cleanup_expired_jobs()
            req_hash = compute_request_hash(request)

            existing_id = self.hash_to_job.get(req_hash)
            if existing_id and existing_id in self.jobs:
                existing_job = self.jobs[existing_id]
                age_s = (datetime.now(timezone.utc) - existing_job.created_at_utc).total_seconds()
                if age_s < 60.0 and existing_job.status in ("queued", "running", "done"):
                    logger.info("Re-using recent job %s for identical request hash", existing_id)
                    return existing_id

            job_id = str(uuid.uuid4())
            record = JobRecord(job_id=job_id, input_hash=req_hash, request=request)
            self.jobs[job_id] = record
            self.hash_to_job[req_hash] = job_id

        # Dispatch execution in background thread
        self.executor.submit(self._run_job, job_id)
        return job_id

    def store_external_job(self, result: PipelineResult, request: PlanRequest) -> str:
        """Store an externally completed simulation (e.g. from monitor tick) as a done job."""
        with self._lock:
            job_id = str(uuid.uuid4())
            req_hash = compute_request_hash(request)
            plan_res = self._convert_pipeline_to_plan_result(result, request)

            rec = JobRecord(
                job_id=job_id,
                input_hash=req_hash,
                request=request,
                status="done",
                stage="Completed",
                progress=1.0,
                trace=plan_res.trace if hasattr(plan_res, "trace") else [],
                result=plan_res,
            )
            self.jobs[job_id] = rec
            self.hash_to_job[req_hash] = job_id
            return job_id

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Retrieve job record by ID."""
        with self._lock:
            return self.jobs.get(job_id)

    def _convert_pipeline_to_plan_result(self, res: PipelineResult, req: PlanRequest) -> PlanResult:
        """Transform raw internal PipelineResult into user-facing PlanResult schema."""
        aoi_model = AOIModel(
            west=res.aoi.west,
            south=res.aoi.south,
            east=res.aoi.east,
            north=res.aoi.north,
        )

        grid_model = GridModel(
            res_m=round(float(res.spread.grid.res_m), 1) if res.spread else (req.resolution_m or 90),
            nx=int(res.spread.grid.nx) if res.spread else 0,
            ny=int(res.spread.grid.ny) if res.spread else 0,
        )

        # Wind model conversion
        wind_now = WindNowModel(
            speed_ms=round(res.wind.speed_ms[0], 1) if res.wind.speed_ms else 0.0,
            dir_from_deg=round(res.wind.dir_from_deg[0], 1) if res.wind.dir_from_deg else 0.0,
            rh=round(res.wind.rh[0], 1) if res.wind.rh else 0.0,
        )
        series_points: List[WindPointModel] = []
        for i in range(min(24, len(res.wind.speed_ms))):
            t_str = (res.wind.start_utc + timedelta(hours=i)).isoformat()
            series_points.append(
                WindPointModel(
                    t_utc=t_str,
                    speed_ms=round(res.wind.speed_ms[i], 1),
                    dir_from_deg=round(res.wind.dir_from_deg[i], 1),
                    rh=round(res.wind.rh[i], 1) if i < len(res.wind.rh) else 0.0,
                )
            )

        wind_model = WindModel(
            source=res.wind.source,
            is_override=res.wind.is_override,
            is_stale=res.wind.is_stale,
            fetched_at_utc=res.wind.fetched_at_utc.isoformat(),
            now=wind_now,
            series=series_points,
        )

        # GeoJSON converters
        detections_fc = build_detections_geojson(res)
        bands_fc = build_arrival_bands_geojson(res.spread, step_min=30.0)
        # Item 17: Large GeoJSON safeguard
        try:
            bands_size = len(json.dumps(bands_fc).encode("utf-8"))
            if bands_size > 5 * 1024 * 1024:
                logger.warning("Arrival bands GeoJSON exceeded 5MB (%d bytes); coarsening step to 60 min", bands_size)
                bands_fc = build_arrival_bands_geojson(res.spread, step_min=60.0)
                res.warnings.append("Plan response exceeded 5MB; simplified arrival band polygons and coarsened time step to prevent payload overflow.")
        except Exception:
            pass

        settlements_fc = build_settlements_geojson(res)
        routes_fc = build_routes_geojson(res)
        naive_cut_fc = build_naive_cut_segments_geojson(res)
        roads_fc = build_roads_geojson(res)

        # Briefing synthesis
        facts = build_facts(res)
        briefing_text = template_briefing(facts)
        used_llm = False
        provider = "Template"
        model = "Deterministic"

        try:
            from core.agent.llm import is_available
            if is_available():
                from core.agent.briefing import briefing_messages
                b_msgs = briefing_messages(facts)
                llm_resp = chat(messages=b_msgs, role="briefing", max_tokens=350)
                guard_out = verify(llm_resp.text or "", facts)
                if guard_out.ok:
                    briefing_text = guard_out.clean_text
                    used_llm = True
                    provider = llm_resp.provider
                    model = llm_resp.model
        except Exception:
            pass

        briefing_model = BriefingModel(
            text=briefing_text,
            used_llm=used_llm,
            provider=provider,
            model=model,
            dropped_sentences=0,
            facts=facts,
        )

        # Provenance records
        prov_list: List[ProvenanceModel] = []
        now_utc = datetime.now(timezone.utc)
        for p in res.provenance:
            age_s = max(0, int((now_utc - p.fetched_at_utc).total_seconds()))
            prov_list.append(
                ProvenanceModel(
                    name=p.name,
                    source=p.source,
                    url=p.url,
                    fetched_at_utc=p.fetched_at_utc.isoformat(),
                    age_s=age_s,
                    ttl_s=p.ttl_s,
                    is_stale=p.is_stale,
                    note=p.note,
                )
            )

        # Trace steps
        trace_list: List[TraceStepModel] = []
        for t in res.trace:
            trace_list.append(
                TraceStepModel(
                    ts_utc=t.get("ts_utc", now_utc.isoformat()),
                    step=t.get("step", "step"),
                    tool=t.get("tool"),
                    status=t.get("status", "ok"),
                    duration_ms=t.get("duration_ms", 0.0),
                    note=t.get("note"),
                )
            )

        return PlanResult(
            mode=res.mode,
            aoi=aoi_model,
            grid=grid_model,
            wind=wind_model,
            detections=detections_fc,
            arrival_bands=bands_fc,
            settlements=settlements_fc,
            routes=routes_fc,
            naive_cut_segments=naive_cut_fc,
            roads=roads_fc,
            metrics=res.metrics,
            briefing=briefing_model,
            provenance=prov_list,
            warnings=res.warnings,
            trace=trace_list,
        )

    def _run_job(self, job_id: str) -> None:
        """Worker thread executing the pipeline."""
        with self._execution_semaphore:
            job = self.get_job(job_id)
            if not job:
                return

            job.status = "running"
            job.stage = "Initializing simulation environment"
            job.progress = 0.1

            req = job.request
            box = AOI(
                west=req.aoi.west,
                south=req.aoi.south,
                east=req.aoi.east,
                north=req.aoi.north,
            )
            ign_pt = (req.ignition.lat, req.ignition.lon) if req.ignition else None
            wind_over = (
                {"speed_ms": req.wind_override.speed_ms, "dir_from_deg": req.wind_override.dir_from_deg}
                if req.wind_override
                else None
            )

            def _update_job_stage(stage_title: str, progress_fraction: float):
                job.stage = stage_title
                job.progress = max(job.progress, round(progress_fraction, 2))

            try:
                job.stage = "Initializing simulation feeds"
                job.progress = 0.12

                res = run_pipeline(
                    aoi=box,
                    mode=req.mode,
                    ignition_point=ign_pt,
                    wind_override=wind_over,
                    resolution_m=req.resolution_m,
                    bypass_cache=False,
                    on_progress=_update_job_stage,
                )

                job.stage = "Formatting response and generating briefing"
                job.progress = 0.90

                plan_result = self._convert_pipeline_to_plan_result(res, req)
                job.result = plan_result
                job.trace = plan_result.trace
                job.status = "done"
                job.stage = "Completed"
                job.progress = 1.0

            except (NoActiveFireError, PipelineError, FeedError) as err:
                logger.warning("Job %s failed with expected pipeline error: %s", job_id, err)
                code = getattr(err, "code", "INTERNAL")
                if code == "NO_FIRE" or isinstance(err, NoActiveFireError):
                    code = "NEEDS_SCENARIO"
                job.status = "error"
                job.stage = "Failed"
                job.error = ErrorDetail(code=str(code), message=str(err))
            except Exception as exc:
                logger.exception("Job %s encountered unexpected failure: %s", job_id, exc)
                job.status = "error"
                job.stage = "Failed"
                job.error = ErrorDetail(code="INTERNAL", message=str(exc))

