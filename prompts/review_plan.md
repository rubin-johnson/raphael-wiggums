You are reviewing an implementation plan for a software project.

## Plan Under Review

{plan}

## Execution State

{state_summary}

## Your Task

Evaluate the plan and return structured feedback covering:

1. **Story completeness** — does each story have acceptance criteria, unit tests, implementation notes, and explicit dependencies?
2. **Dependency correctness** — are dependencies listed in the right direction? Any cycles or missing dependencies?
3. **Story sizing** — are any stories too large to complete in a single Claude Code context window (~10k tokens of work)?
4. **Coverage gaps** — what important functionality is missing from the plan?
5. **Ordering** — given the dependencies, is the execution order sensible?

After the analysis, output:
- A numbered list of **issues found** (severity: HIGH / MEDIUM / LOW)
- A numbered list of **suggested improvements**
- If you were to rewrite this plan to fix the issues, output the full corrected plan.md between these exact markers:
  ```
  ===REWRITTEN_PLAN_START===
  <full corrected plan.md here>
  ===REWRITTEN_PLAN_END===
  ```
  Only include the rewrite block if significant changes are needed.
