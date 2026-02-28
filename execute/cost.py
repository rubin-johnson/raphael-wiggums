"""
Model escalation schedule and cost parsing.

--model-escalation format: "sonnet:3,opus:2"
Means: try up to 3 times on sonnet, then up to 2 more times on opus.
Default: "sonnet:3" (no escalation).
"""
from dataclasses import dataclass


@dataclass
class ModelTier:
    model: str
    max_attempts: int


def parse_escalation(spec: str) -> list[ModelTier]:
    """Parse 'sonnet:3,opus:2' into list of ModelTier."""
    tiers = []
    for part in spec.split(","):
        part = part.strip()
        if ":" in part:
            model, n = part.rsplit(":", 1)
            tiers.append(ModelTier(model=model.strip(), max_attempts=int(n.strip())))
        else:
            # No count specified — unlimited
            tiers.append(ModelTier(model=part.strip(), max_attempts=999))
    return tiers


def model_for_attempt(tiers: list[ModelTier], attempt: int) -> str:
    """
    Given 1-based attempt number and escalation tiers, return the model to use.

    Example: tiers=[sonnet:3, opus:2], attempt=4 → opus
    """
    cumulative = 0
    for tier in tiers:
        cumulative += tier.max_attempts
        if attempt <= cumulative:
            return tier.model
    # Beyond all tiers — use last tier's model
    return tiers[-1].model


def total_max_retries(tiers: list[ModelTier]) -> int:
    """Total attempts across all tiers, minus 1 (first attempt isn't a retry)."""
    total = sum(t.max_attempts for t in tiers)
    return max(0, total - 1)
