"""Background autonomous monitoring task for EmberRoute.

Periodically queries environmental feeds and runs orchestrator.tick()
in the executor thread pool. Updates status and stores any newly generated
evaluations as accessible jobs.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional

from api.jobs import JobManager
from api.schemas import AOIModel, MonitorRequest, MonitorStatusResponse, PlanRequest
from core.agent.orchestrator import Orchestrator
from core.models import AOI

logger = logging.getLogger(__name__)


class MonitorManager:
    """Manages the background monitor task."""

    def __init__(self, job_manager: JobManager) -> None:
        self.job_manager = job_manager
        self.orchestrator: Optional[Orchestrator] = None
        self.task: Optional[asyncio.Task] = None
        self.enabled: bool = False
        self.last_cycle_utc: Optional[str] = None
        self.last_reasons: List[str] = []
        self.current_job_id: Optional[str] = None
        self.next_poll_utc: Optional[str] = None
        self.poll_s: int = 60
        self.current_req: Optional[PlanRequest] = None

    def get_status(self) -> MonitorStatusResponse:
        """Return the current monitoring status."""
        return MonitorStatusResponse(
            enabled=self.enabled,
            last_cycle_utc=self.last_cycle_utc,
            last_reasons=self.last_reasons,
            current_job_id=self.current_job_id,
            next_poll_utc=self.next_poll_utc,
        )

    def configure(self, req: MonitorRequest) -> MonitorStatusResponse:
        """Enable or disable autonomous background polling."""
        if req.enabled:
            self.poll_s = req.poll_s or 60
            aoi_obj = (
                AOI(west=req.aoi.west, south=req.aoi.south, east=req.aoi.east, north=req.aoi.north)
                if req.aoi
                else AOI(west=7.45, south=46.20, east=7.65, north=46.35)
            )
            mode = req.mode or "LIVE"
            self.orchestrator = Orchestrator(aoi=aoi_obj, mode=mode)
            self.current_req = PlanRequest(
                aoi=req.aoi or AOIModel(west=7.45, south=46.20, east=7.65, north=46.35),
                mode=mode,
                ignition=req.ignition,
                wind_override=req.wind_override,
            )

            # Cancel existing task if running
            if self.task and not self.task.done():
                self.task.cancel()

            self.enabled = True
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            self.task = loop.create_task(self._monitor_loop())
            logger.info("Autonomous monitor enabled with poll_s=%d", self.poll_s)
        else:
            self.enabled = False
            if self.task and not self.task.done():
                self.task.cancel()
                self.task = None
            self.next_poll_utc = None
            logger.info("Autonomous monitor disabled")

        return self.get_status()

    async def shutdown(self) -> None:
        """Gracefully terminate background monitor upon server shutdown."""
        self.enabled = False
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def _monitor_loop(self) -> None:
        """Main polling loop running in the asyncio event loop."""
        while self.enabled:
            now = datetime.now(timezone.utc)
            self.next_poll_utc = (now + timedelta(seconds=self.poll_s)).isoformat()

            try:
                loop = asyncio.get_running_loop()
                # Run orchestrator.tick() inside executor to avoid blocking event loop
                tick_res = await loop.run_in_executor(
                    self.job_manager.executor,
                    self.orchestrator.tick,
                )

                self.last_cycle_utc = datetime.now(timezone.utc).isoformat()
                self.last_reasons = tick_res.reasons

                if tick_res.cycle_result and tick_res.cycle_result.result:
                    # Register evaluation as an accessible job
                    job_id = self.job_manager.store_external_job(
                        result=tick_res.cycle_result.result,
                        request=self.current_req,
                    )
                    self.current_job_id = job_id
                    logger.info("Monitor generated new evaluation job: %s", job_id)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Monitor tick encountered error: %s", exc)

            await asyncio.sleep(self.poll_s)

