"""CLI Health Check script for EmberRoute data feeds.

Prints a formatted status table of all upstream dependencies.
Exits with code 1 if FIRMS or Open-Meteo is unavailable; otherwise exits 0.
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.data.health import check_all


def main() -> None:
    print("=" * 80)
    print("           EMBERROUTE UPSTREAM DATA FEED HEALTH REPORT           ")
    print("=" * 80)

    results = check_all()

    header = f"{'Feed Name':<15} | {'Status':<8} | {'Latency':<10} | {'Details'}"
    print(header)
    print("-" * 80)

    critical_failure = False

    for feed, info in results.items():
        status_str = "OK" if info["ok"] else "DOWN"
        latency_str = f"{info['latency_ms']:.1f} ms"
        detail_str = info["detail"]

        row = f"{feed:<15} | {status_str:<8} | {latency_str:<10} | {detail_str}"
        print(row)

        if feed in ("firms", "open_meteo") and not info["ok"]:
            critical_failure = True

    print("=" * 80)

    if critical_failure:
        print("ERROR: One or more critical live data feeds (FIRMS, Open-Meteo) are DOWN.")
        sys.exit(1)
    else:
        print("SUCCESS: All critical live feeds are operational.")
        sys.exit(0)


if __name__ == "__main__":
    main()

