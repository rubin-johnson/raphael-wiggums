You are producing a prioritized improvement plan for a codebase.

## Architectural Understanding
{understanding}

## Scoring weights
Score each candidate improvement:
- simplification_value (1-10): how much simpler/cleaner would the code be?
- risk (1-10): how likely to introduce bugs? (lower = safer)
- effort (1-10): how much work? (lower = less work)
- net_score: (simplification_value x 2) - risk - effort

Feature additions score 0 on simplification_value unless they replace existing complexity.

## Your Task

### Current State Assessment
Honest 2-3 paragraph summary of quality, with evidence from the understanding doc.

### Prioritized Improvements
Ordered by net_score descending. Each entry must include:
- What exactly changes (specific files and functions)
- Why this is an improvement (what problem it solves)
- Rough net_score: simplification_value, risk, effort
- Whether this could be a single Raphael story or needs splitting

### What To Leave Alone
Things that might look improvable but shouldn't be touched, and why.

Be ruthless. The goal is less code that does the same thing, not more features.
