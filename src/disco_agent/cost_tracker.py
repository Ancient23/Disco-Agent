from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CostTracker:
    def __init__(self, warning_threshold_usd: float):
        self.warning_threshold_usd = warning_threshold_usd
        self.total_cost_usd: float = 0.0
        self.warning_emitted: bool = False

    def add_cost(self, cost_usd: float) -> list[str]:
        self.total_cost_usd += cost_usd
        warnings: list[str] = []

        if (
            not self.warning_emitted
            and self.total_cost_usd >= self.warning_threshold_usd
        ):
            self.warning_emitted = True
            msg = (
                f"Budget warning: session cost ${self.total_cost_usd:.2f} "
                f"has exceeded threshold ${self.warning_threshold_usd:.2f}"
            )
            logger.warning(msg)
            warnings.append(msg)

        return warnings
