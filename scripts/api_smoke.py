"""Smoke test script for EmberRoute FastAPI server.

Runs against a live server (default http://127.0.0.1:8000):
1. Verifies health endpoint.
2. Checks active fire clusters scan.
3. Submits SCENARIO plan job with ignition & wind override.
4. Polls job to completion, tracking live progress.
5. Validates JSON payload against Pydantic schema.
6. Tests monitor status, assumptions, and validation endpoints.
7. Prints timing, OpenAPI schema size, and PASS/FAIL table. Exits non-zero on failure.
"""

from pathlib import Path
import sys
import time
from typing import Any, Dict, List
import httpx

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from api.schemas import HealthResponse, JobStatusResponse, PlanResult


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    base_url = base_url.rstrip("/")

    print("=" * 75)
    print("EMBERROUTE API SMOKE TEST")
    print("=" * 75)
    print(f"Target Base URL: {base_url}\n")

    start_total = time.perf_counter()
    results_table: List[tuple[str, str, str]] = []
    all_passed = True

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        # 1. Root / Docs / OpenAPI Check
        print("[Step 1] Checking root and OpenAPI specification...")
        try:
            openapi_resp = client.get("/openapi.json")
            if openapi_resp.status_code == 200:
                schema_size_kb = len(openapi_resp.content) / 1024.0
                results_table.append(("OpenAPI Schema", "PASS", f"{schema_size_kb:.1f} KB generated"))
                print(f"  OpenAPI schema size: {schema_size_kb:.1f} KB")
            else:
                results_table.append(("OpenAPI Schema", "FAIL", f"HTTP {openapi_resp.status_code}"))
                all_passed = False
        except Exception as exc:
            results_table.append(("OpenAPI Schema", "FAIL", str(exc)))
            all_passed = False

        # 2. Health Endpoint
        print("\n[Step 2] Testing GET /api/health...")
        try:
            h_resp = client.get("/api/health")
            if h_resp.status_code == 200:
                h_data = h_resp.json()
                # Validate against schema
                HealthResponse.model_validate(h_data)
                feed_count = len(h_data.get("feeds", {}))
                results_table.append(("Health Endpoint", "PASS", f"{feed_count} feeds reported"))
                print(f"  Health OK: {feed_count} feeds diagnosed")
            else:
                results_table.append(("Health Endpoint", "FAIL", f"HTTP {h_resp.status_code}"))
                all_passed = False
        except Exception as exc:
            results_table.append(("Health Endpoint", "FAIL", str(exc)))
            all_passed = False

        # 3. Clusters Endpoint
        print("\n[Step 3] Testing GET /api/clusters...")
        try:
            c_resp = client.get("/api/clusters?hours=24")
            if c_resp.status_code == 200:
                clusters = c_resp.json()
                results_table.append(("Clusters Endpoint", "PASS", f"{len(clusters)} clusters found"))
                print(f"  Clusters OK: {len(clusters)} active clusters returned")
            else:
                results_table.append(("Clusters Endpoint", "FAIL", f"HTTP {c_resp.status_code}"))
                all_passed = False
        except Exception as exc:
            results_table.append(("Clusters Endpoint", "FAIL", str(exc)))
            all_passed = False

        # 4. Submit Simulation Plan (POST /api/plan)
        print("\n[Step 4] Submitting simulation job (POST /api/plan)...")
        job_id = None
        try:
            plan_body = {
                "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
                "mode": "SCENARIO",
                "ignition": {"lat": 46.28, "lon": 7.55},
                "wind_override": {"speed_ms": 7.0, "dir_from_deg": 240.0},
                "resolution_m": 90,
            }
            t0 = time.perf_counter()
            p_resp = client.post("/api/plan", json=plan_body)
            lat_submit = (time.perf_counter() - t0) * 1000.0

            if p_resp.status_code == 202:
                job_id = p_resp.json().get("job_id")
                results_table.append(("Plan Submission", "PASS", f"job_id={job_id} in {lat_submit:.1f}ms"))
                print(f"  Job Accepted (202): {job_id}")
            else:
                results_table.append(("Plan Submission", "FAIL", f"HTTP {p_resp.status_code}"))
                all_passed = False
        except Exception as exc:
            results_table.append(("Plan Submission", "FAIL", str(exc)))
            all_passed = False

        # 5. Poll Job Until Completion (GET /api/jobs/{id})
        if job_id:
            print(f"\n[Step 5] Polling GET /api/jobs/{job_id}...")
            poll_start = time.perf_counter()
            job_done = False
            last_stage = ""

            while time.perf_counter() - poll_start < 180.0:
                try:
                    poll_resp = client.get(f"/api/jobs/{job_id}")
                    if poll_resp.status_code != 200:
                        print(f"  Poll returned HTTP {poll_resp.status_code}")
                        time.sleep(1.0)
                        continue

                    job_data = poll_resp.json()
                    st = job_data.get("status")
                    cur_stage = job_data.get("stage", "")
                    progress = job_data.get("progress", 0.0)

                    if cur_stage != last_stage:
                        print(f"  Stage: {cur_stage:<45} Progress: {progress*100:>5.1f}%")
                        last_stage = cur_stage

                    if st == "done":
                        job_done = True
                        poll_duration = time.perf_counter() - poll_start
                        res_obj = job_data.get("result")

                        # Validate result against Pydantic schema
                        PlanResult.model_validate(res_obj)

                        metrics = res_obj.get("metrics", {})
                        n_threat = metrics.get("n_threatened", 0)
                        n_evac = metrics.get("n_evacuate", 0)
                        n_settle = metrics.get("n_settlements_total", 0)

                        results_table.append((
                            "Job Execution & Schema",
                            "PASS",
                            f"{poll_duration:.1f}s, {n_settle} settlements, {n_threat} threatened, {n_evac} evacuate",
                        ))
                        break
                    elif st == "error":
                        err_info = job_data.get("error", {})
                        results_table.append(("Job Execution", "FAIL", f"Job failed: {err_info}"))
                        all_passed = False
                        break

                    time.sleep(1.0)
                except Exception as exc:
                    print(f"  Polling exception: {exc}")
                    time.sleep(1.0)

            if not job_done and all_passed:
                results_table.append(("Job Polling", "FAIL", "Timed out after 180s"))
                all_passed = False

        # 6. Monitor & Assumptions & Validation Endpoints
        print("\n[Step 6] Testing auxiliary endpoints...")
        try:
            m_resp = client.get("/api/monitor")
            assert m_resp.status_code == 200
            results_table.append(("GET /api/monitor", "PASS", f"enabled={m_resp.json().get('enabled')}"))
        except Exception as exc:
            results_table.append(("GET /api/monitor", "FAIL", str(exc)))
            all_passed = False

        try:
            a_resp = client.get("/api/assumptions")
            assert a_resp.status_code == 200
            txt_len = len(a_resp.json().get("text", ""))
            results_table.append(("GET /api/assumptions", "PASS", f"{txt_len} chars text"))
        except Exception as exc:
            results_table.append(("GET /api/assumptions", "FAIL", str(exc)))
            all_passed = False

        try:
            v_resp = client.get("/api/validation")
            assert v_resp.status_code == 200
            v_data = v_resp.json()
            results_table.append(("GET /api/validation", "PASS", f"available={v_data.get('available')}, {len(v_data.get('events', []))} events"))
        except Exception as exc:
            results_table.append(("GET /api/validation", "FAIL", str(exc)))
            all_passed = False

    # Summary
    total_time = time.perf_counter() - start_total
    print("\n" + "=" * 75)
    print(f"{'Endpoint / Check':<25} {'Result':<10} {'Details'}")
    print("-" * 75)
    for name, res_str, detail in results_table:
        print(f"{name:<25} {res_str:<10} {detail}")
    print("=" * 75)
    print(f"Total API Smoke Runtime: {total_time:.2f} s")

    if all_passed:
        print("OVERALL STATUS: PASS")
        return 0
    else:
        print("OVERALL STATUS: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())

