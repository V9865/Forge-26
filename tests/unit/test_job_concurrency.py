"""Test that JobManager restricts simultaneous pipeline executions to 1 and queues subsequent jobs."""

import time
from unittest.mock import patch
import pytest

from api.jobs import JobManager
from api.schemas import AOIModel, PlanRequest


class MockPlanResult:
    trace = []


def test_job_manager_queues_second_job():
    """Verify that when 2 jobs are submitted, the second waits in 'queued' until the first completes."""
    manager = JobManager(max_workers=1)

    req1 = PlanRequest(
        aoi=AOIModel(west=1.0, south=1.0, east=1.2, north=1.2),
        mode="SCENARIO",
        ignition={"lat": 1.1, "lon": 1.1},
    )
    req2 = PlanRequest(
        aoi=AOIModel(west=2.0, south=2.0, east=2.2, north=2.2),
        mode="SCENARIO",
        ignition={"lat": 2.1, "lon": 2.1},
    )

    execution_order = []

    def mock_run_pipeline(*args, **kwargs):
        aoi = kwargs.get("aoi")
        tag = f"aoi_{aoi.west}"
        execution_order.append(f"{tag}_start")
        time.sleep(0.4)
        execution_order.append(f"{tag}_end")

        class MockResult:
            def __init__(self):
                self.plans = []
                self.metrics = {"n_threatened": 0}
                self.warnings = []
                self.trace = []
                self.roads = []
                self.detections = []
                self.wind = None
                self.spread = None
                self.grid = None
                self.aoi = None
                self.mode = "SCENARIO"
                self.provenance = []

        return MockResult()

    with patch("api.jobs.run_pipeline", side_effect=mock_run_pipeline), \
         patch.object(manager, "_convert_pipeline_to_plan_result", return_value=MockPlanResult()):

        jid1 = manager.submit(req1)
        jid2 = manager.submit(req2)

        # Allow worker thread 1 to start
        time.sleep(0.1)

        j1 = manager.get_job(jid1)
        j2 = manager.get_job(jid2)

        # J1 should be running, J2 must be queued!
        assert j1.status in ("running", "done")
        assert j2.status == "queued"

        # Wait for both to complete
        for _ in range(30):
            time.sleep(0.1)
            if manager.get_job(jid1).status in ("done", "error") and manager.get_job(jid2).status in ("done", "error"):
                break

        assert manager.get_job(jid1).status == "done"
        assert manager.get_job(jid2).status == "done"

        # Sequential non-overlapping execution verification:
        # First job must finish before second job starts!
        assert len(execution_order) == 4
        assert execution_order[0].endswith("_start")
        assert execution_order[1].endswith("_end")
        assert execution_order[2].endswith("_start")
        assert execution_order[3].endswith("_end")
        assert execution_order[0].split("_")[1] == execution_order[1].split("_")[1]
        assert execution_order[2].split("_")[1] == execution_order[3].split("_")[1]
        assert execution_order[0] != execution_order[2]
