You are analyzing a single Python module to produce structured understanding.

## File: {filename}

## Repo Map Context (surrounding codebase structure)
{repo_map}

## File Content
{content}

## Your Task
Return a JSON object with exactly these fields (no markdown code blocks, no explanation):
{{
  "file": "<relative path>",
  "purpose": "<one sentence: what does this module do?>",
  "public_api": ["<public functions/classes a caller would use>"],
  "data_flow": "<how data enters, transforms, and leaves this module>",
  "internal_dependencies": ["<imports from within this repo>"],
  "external_dependencies": ["<third-party imports>"],
  "complexity_signals": ["<what makes this module hard to understand or change>"],
  "smells": ["<duplication, tight coupling, misleading names, etc>"],
  "simplification_opportunities": ["<specific things that could be removed or simplified>"],
  "test_coverage_estimate": "none|low|medium|high",
  "lines_of_code": <integer>
}}

Return ONLY valid JSON. No prose, no markdown fences.
