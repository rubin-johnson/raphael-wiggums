You are reviewing an architectural understanding document for accuracy and usefulness.

## Repo Map (ground truth — use this to verify accuracy)
{repo_map}

## Understanding Document Under Review
{understanding}

## Your Task
Score this document. Return ONLY valid JSON, no prose, no markdown fences:
{{
  "accuracy": <1-10, does it correctly reflect the repo map structure?>,
  "specificity": <1-10, does it name specific files/functions or give vague generic advice?>,
  "actionability": <1-10, are the simplification opportunities concrete and implementable?>,
  "overall": <integer average of the three scores>,
  "pass": <true if overall >= 7, false otherwise>,
  "issues": ["<specific problems with this understanding document>"],
  "missing": ["<important things present in the repo map that were not identified>"]
}}
