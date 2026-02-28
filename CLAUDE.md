# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project: learning_2_ralph

Exploratory project for building a PRD-to-story pipeline ("Ralph Wiggum flow") — converting product requirements into individually-completeable implementation stories.

---

## Core Concepts

### The Ralph Wiggum Flow
A local script pipeline that:
1. Takes input (voice or text) via **whisperflow**
2. Converts it through a **Ralph PRD converter** (rough idea → structured PRD)
3. Generates stories from the PRD, each scoped to one context window
4. Emits stories with acceptance criteria, ordered dependencies-first

### Story Constraints
- Each story must be completeable in a **single Claude Code context window**
- Dependencies must be resolved before the story that requires them
- Every story needs explicit **acceptance criteria**

### Key Terms
- **whisperflow**: Voice-to-text input pipeline (important — likely the entry point)
- **AMP**: TBD — investigate what this refers to in the PRD/story context
- **PRD**: Product Requirements Document — structured spec that precedes story generation
- **Ralph PRD converter**: Tool that converts raw notes/voice into a structured PRD

---

## Architecture (Intended)

```
[Voice/Text Input]
       ↓
  whisperflow
       ↓
  PRD Generator / Ralph PRD Converter
       ↓
  Story Splitter (one-context-window constraint)
       ↓
  [Stories with acceptance criteria, dependency-ordered]
```

---

## Open Questions

- What is AMP in this context?
- What format does whisperflow output?
- Is the PRD generator an LLM call, a template, or structured extraction?
- What triggers the flow — CLI script, file watcher, webhook?
