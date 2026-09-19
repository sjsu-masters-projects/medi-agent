"""Agent runtime: the routing table, model transports, plugins, agents, and tools.

This package is the single place that answers "which model runs this workload, how long
may it take, and what happens when it does not answer". Callers ask the registry rather
than constructing a client, so a routing change is a data change in one file instead of
an edit spread across agent graphs.
"""

from app.adk.registry import (
    Transport,
    Workload,
    WorkloadRoute,
    route_for,
    routes,
)
from app.adk.runner import (
    REQUIRED_PLUGIN_NAMES,
    MissingRuntimeGuaranteeError,
    assert_guarantees,
    build_runner,
)

__all__ = [
    "REQUIRED_PLUGIN_NAMES",
    "MissingRuntimeGuaranteeError",
    "Transport",
    "Workload",
    "WorkloadRoute",
    "assert_guarantees",
    "build_runner",
    "route_for",
    "routes",
]
