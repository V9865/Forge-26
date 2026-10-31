"""EmberRoute evacuation package.

Exposes graph annotation, time-dependent routing, and naive baseline comparison.
"""

from core.evac.graph_prep import annotate_edges, compute_safe_targets
from core.evac.naive import compare, naive_route, route_is_cut
from core.evac.planner import earliest_safe_route, latest_departure, plan_settlements

__all__ = [
    "annotate_edges",
    "compute_safe_targets",
    "earliest_safe_route",
    "latest_departure",
    "plan_settlements",
    "naive_route",
    "route_is_cut",
    "compare",
]

