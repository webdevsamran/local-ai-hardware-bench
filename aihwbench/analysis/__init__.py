"""Analysis engines: fit estimation, recommendations, bottleneck analysis,
thermal stability, energy accounting, and cost/TCO (#20-#26).

Every function separates *measured facts* from *estimates*. Estimates are
always returned under keys prefixed ``estimated_`` with their assumptions
recorded alongside; measured values stay ``None`` when unavailable.
"""

from __future__ import annotations

from .analyze import analyze_bottlenecks
from .cost import compute_cost_metrics
from .energy import compute_energy_metrics
from .fit import estimate_model_fit
from .recommend import recommend_configuration
from .thermal import analyze_thermal_stability

__all__ = [
    "analyze_bottlenecks",
    "compute_cost_metrics",
    "compute_energy_metrics",
    "estimate_model_fit",
    "recommend_configuration",
    "analyze_thermal_stability",
]
