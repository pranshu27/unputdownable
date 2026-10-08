---
name: langsmith-fetch
description: Debug LangChain and LangGraph agents by fetching execution traces from LangSmith. Use this when investigating failures, incorrect tool usage, memory behavior, or performance regressions.
---

# LangSmith Fetch Debug Skill

Use this skill to inspect LangSmith traces from CLI and turn trace data into actionable debugging guidance.

## When to use

Use when the user asks things like:
- "Debug my agent"
- "Why did this fail?"
- "Show recent traces"
- "Which tools were called?"
- "Why is memory not working?"
- "Why is it slow?"

## Prerequisites

1. Install CLI:
```bash
pip install langsmith-fetch
```

2. Set environment:
```bash
export LANGSMITH_API_KEY="your_key"
export LANGSMITH_PROJECT="your_project"
```

3. Verify:
```bash
echo $LANGSMITH_API_KEY
echo $LANGSMITH_PROJECT
```

## Core workflows

### 1) Quick recent debug

```bash
langsmith-fetch traces --last-n-minutes 5 --limit 5 --format pretty
```

Report:
- trace count
- failures and error messages
- tools called
- execution durations
- token usage

### 2) Deep dive a specific trace

```bash
langsmith-fetch trace <trace-id> --format json
```

Report:
- user intent / agent goal
- tool call sequence
- first failing step
- root cause
- suggested fix

### 3) Export a debug session

```bash
SESSION_DIR="langsmith-debug/session-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$SESSION_DIR"
langsmith-fetch traces "$SESSION_DIR/traces" --last-n-minutes 30 --limit 50 --include-metadata
langsmith-fetch threads "$SESSION_DIR/threads" --limit 20
```

### 4) Error sweep

```bash
langsmith-fetch traces --last-n-minutes 30 --limit 50 --format json > recent-traces.json
grep -i "error\|failed\|exception" recent-traces.json
```

Summarize:
- failure rate
- top error classes
- failing agent/tool combinations
- time patterns and recurring causes

## Common troubleshooting playbook

### No traces found

Possible causes:
- no recent activity
- tracing disabled
- wrong project
- API key/config issue

Try:
```bash
langsmith-fetch traces --last-n-minutes 1440 --limit 50
langsmith-fetch config show
langsmith-fetch threads --limit 10
```

### Project not found

```bash
langsmith-fetch config show
export LANGSMITH_PROJECT="correct-project-name"
langsmith-fetch config set project "correct-project-name"
```

### Environment not persisting

Add exports to shell profile and reload it.

## Output format guidance

- `--format pretty`: quick human review
- `--format json`: deep analysis and structured inspection
- `--format raw`: piping into other shell tools

## Quick reference

```bash
# recent traces
langsmith-fetch traces --last-n-minutes 5 --limit 5 --format pretty

# specific trace
langsmith-fetch trace <trace-id> --format pretty

# export session
langsmith-fetch traces ./debug-session --last-n-minutes 30 --limit 50

# with metadata
langsmith-fetch traces --limit 10 --include-metadata
```

## Suggested response template

When reporting, keep this structure:
1. What was requested
2. What ran (trace + tools)
3. What failed (or what was slow)
4. Root cause
5. Concrete next fix steps

## Learnings

- Always fetch traces first before theorizing about agent failures.
- For "wrong tool" reports, inspect tool descriptions and call sequence in the trace before changing prompts.
- For memory issues, confirm both memory write and memory read paths were executed in trace data.
