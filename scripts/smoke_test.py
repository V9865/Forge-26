"""Container and deployment smoke test for EmberRoute.

Validates:
1. Container reachability and root endpoint (GET /).
2. Live feed health checks and diagnostics (GET /api/health).
3. Real end-to-end plan execution (POST /api/plan and polling GET /api/jobs/{id}).
4. Pydantic schema validation of PlanResult.
5. Measures cold start and first plan execution time.
6. Prints PASS/FAIL summary table and exits non-zero on failure.
"""

from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional
import httpx

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from api.schemas import HealthResponse, JobStatusResponse, PlanResult


def main() -> int:
    # Accept URL from CLI argument, environment variable, or default to localhost:7860
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7860"
    base_url = base_url.rstrip("/")

    print("=" * 75)
    print("EMBERROUTE CONTAINER & DEPLOYMENT SMOKE TEST")
    print("=" * 75)
    print(f"Target Base URL: {base_url}\n")

    start_total = time.perf_counter()
    results_table: List[tuple[str, str, str]] = []
    all_passed = True

    cold_start_s = 0.0
    first_plan_s = 0.0

    with httpx.Client(base_url=base_url, timeout=45.0) as client:
        # 1. Cold Start & Root Endpoint Check
        print("[Step 1] Probing container root endpoint (GET /)...")
        t0 = time.perf_counter()
        try:
            root_resp = client.get("/")
            cold_start_s = time.perf_counter() - t0
            if root_resp.status_code == 200:
                is_html = "text/html" in root_resp.headers.get("content-type", "")
                detail_str = "React frontend index.html" if is_html else "API JSON fallback"
                results_table.append(("Root Endpoint (GET /)", "PASS", f"{detail_str} (cold start {cold_start_s:.2f}s)"))
                print(f"  Root Reachable ({root_resp.status_code}): {detail_str} in {cold_start_s:.2f}s")
            else:
                results_table.append(("Root Endpoint (GET /)", "FAIL", f"HTTP {root_resp.status_code}"))
                all_passed = False
        except Exception as exc:
            results_table.append(("Root Endpoint (GET /)", "FAIL", f"Connection error: {exc}"))
            all_passed = False

        # 2. Health Check Endpoint
        print("\n[Step 2] Querying system diagnostics (GET /api/health)...")
        try:
            h_resp = client.get("/api/health")
            if h_resp.status_code == 200:
                h_data = h_resp.json()
                HealthResponse.model_validate(h_data)
                feed_count = len(h_data.get("feeds", {}))
                results_table.append(("Health Endpoint", "PASS", f"{feed_count} feeds reported"))
                print(f"  Health Check Passed: {feed_count} upstream feeds diagnosed")
            else:
                results_table.append(("Health Endpoint", "FAIL", f"HTTP {h_resp.status_code}"))
                all_passed = False
        except Exception as exc:
            results_table.append(("Health Endpoint", "FAIL", str(exc)))
            all_passed = False

        # 3. Real Plan Execution (POST /api/plan -> Poll GET /api/jobs/{id})
        print("\n[Step 3] Submitting simulation plan to container (POST /api/plan)...")
        job_id: Optional[str] = None
        plan_body = {
            "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
            "mode": "SCENARIO",
            "ignition": {"lat": 46.28, "lon": 7.55},
            "wind_override": {"speed_ms": 7.0, "dir_from_deg": 240.0},
            "resolution_m": 90,
        }

        try:
            t_plan_submit = time.perf_counter()
            p_resp = client.post("/api/plan", json=plan_body)
            if p_resp.status_code == 202:
                job_id = p_resp.json().get("job_id")
                results_table.append(("Plan Submission", "PASS", f"job_id={job_id}"))
                print(f"  Job Queued (202): {job_id}")
            else:
                results_table.append(("Plan Submission", "FAIL", f"HTTP {p_resp.status_code}"))
                all_passed = False
        except Exception as exc:
            results_table.append(("Plan Submission", "FAIL", str(exc)))
            all_passed = False

        # 4. Poll Simulation Job to Completion
        if job_id:
            print(f"\n[Step 4] Polling simulation progress for job {job_id}...")
            t_poll_start = time.perf_counter()
            job_completed = False
            last_stage = ""

            # Poll for up to 180 seconds (covering live data downloads on first run)
            while time.perf_counter() - t_poll_start < 180.0:
                try:
                    job_resp = client.get(f"/api/jobs/{job_id}")
                    if job_resp.status_code != 200:
                        print(f"  Polling returned HTTP {job_resp.status_code}")
                        time.sleep(1.0)
                        continue

                    job_dict = job_resp.json()
                    st = job_dict.get("status")
                    cur_stage = job_dict.get("stage", "")
                    progress = job_dict.get("progress", 0.0)

                    if cur_stage != last_stage:
                        print(f"  Progress: {progress*100:>5.1f}% | Stage: {cur_stage}")
                        last_stage = cur_stage

                    if st == "done":
                        job_completed = True
                        first_plan_s = time.perf_counter() - t_poll_start
                        raw_result = job_dict.get("result")

                        # Validate result schema against Pydantic model
                        PlanResult.model_validate(raw_result)

                        metrics = raw_result.get("metrics", {})
                        n_settle = metrics.get("n_settlements_total", 0)
                        n_threat = metrics.get("n_threatened", 0)
                        n_evac = metrics.get("n_evacuate", 0)

                        results_table.append((
                            "Simulation Execution",
                            "PASS",
                            f"{first_plan_s:.1f}s | {n_settle} settlements, {n_threat} threatened, {n_evac} evacuate",
                        ))
                        print(f"\n  Plan Succeeded in {first_plan_s:.2f}s!")
                        break
                    elif st == "error":
                        err_obj = job_dict.get("error", {})
                        results_table.append(("Simulation Execution", "FAIL", f"Job failed: {err_obj}"))
                        all_passed = False
                        break

                    time.sleep(1.0)
                except Exception as exc:
                    print(f"  Polling error: {exc}")
                    time.sleep(1.0)

            if not job_completed and all_passed:
                results_table.append(("Simulation Execution", "FAIL", "Timed out after 180s"))
                all_passed = False

    # 5. Summary & Timing Report
    total_duration = time.perf_counter() - start_total
    print("\n" + "=" * 75)
    print(f"{'Check / Target':<28} {'Result':<10} {'Details'}")
    print("-" * 75)
    for target, outcome, details in results_table:
        print(f"{target:<28} {outcome:<10} {details}")
    print("=" * 75)
    print(f"Cold Start Time:           {cold_start_s:.2f} s")
    print(f"First Plan Execution Time: {first_plan_s:.2f} s")
    print(f"Total Smoke Test Runtime:  {total_duration:.2f} s")

    if all_passed:
        print("OVERALL STATUS: PASS")
        return 0
    else:
        print("OVERALL STATUS: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())

