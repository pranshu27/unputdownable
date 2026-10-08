# Concepts — Agentic Informatica → PySpark Codegen

A guided tour of every component in this project: the AutoGen runtime primitives, the two
agent collaboration patterns, the message/topic contracts, and — in depth — the
**prompt-engineering** methods that power the LLM agents. For each topic you get a short
explanation, a code example from this repo, and the rationale for the choice made here.

---

## 1. AutoGen Core primitives

### 1.1 `RoutedAgent`
Base class for an agent that routes incoming messages to handler methods by message type.
Every agent here subclasses it.

```python
class PCExtractorAgent(RoutedAgent):
    def __init__(self, model_client):
        super().__init__(description="PowerCenter node metadata extractor")
```

### 1.2 `@message_handler`
Marks an async method as the handler for a given message dataclass. AutoGen dispatches by
the annotated parameter type.

```python
@message_handler
async def handle_node(self, message: PCMessage, ctx: MessageContext) -> None: ...
```

### 1.3 `@type_subscription` / `TypeSubscription`
Binds an agent to a **topic** so it receives anything published to that topic type. This is
the pub/sub backbone of Phase 1.

```python
await runtime.add_subscription(
    TypeSubscription(topic_type=PC_EXTRACTION_TOPIC_TYPE, agent_type="pc_extractor")
)
```

### 1.4 `publish_message` + `TopicId` / `DefaultTopicId`
`publish_message` is **fire-and-forget broadcast** to a topic (1→N). We publish each
extractor result to a response topic the collector listens on.

```python
await self.publish_message(
    result, topic_id=TopicId(PC_EXTRACTION_RESPONSE_TOPIC_TYPE, source=self.id.key)
)
```

### 1.5 `send_message` + `AgentId`
`send_message` is a **direct request/response** call (1→1) that returns the handler's
return value. The orchestrator uses it to call workers and get results back.

```python
result: WorkerTaskResult = await self.send_message(
    WorkerTask(task=json.dumps(node)), AgentId("pyspark_generation", "default")
)
```

> **publish vs send** — publish = broadcast, no return value (good for fan-out + a barrier);
> send = addressed, returns a value (good for orchestrated step-by-step pipelines).

### 1.6 `SingleThreadedAgentRuntime`
Hosts all agents, delivers messages, and runs the event loop. Lifecycle:

```python
runtime = SingleThreadedAgentRuntime()
# ... register agents + subscriptions ...
runtime.start()
# ... publish / send ...
await runtime.stop_when_idle()
```

A single-threaded runtime gives **deterministic, ordered** message delivery — important for
a reproducible code generator.

---

## 2. Collaboration patterns

### 2.1 Pub/Sub + Barrier (Phase 1 — extraction)
Fan every PowerCenter node out to `PCExtractorAgent`, then **synchronize** all responses
with a barrier before moving on. The barrier is a small shared-state object:

```python
class CollectorState:
    def __init__(self):
        self.event = asyncio.Event()
        self.expected_count = 0
        self.response_counter = 0
        self.results = []
```

**Invariant:** call `set_expected_count(n)` **before** publishing the `n` tasks, otherwise a
fast response could fire `event.set()` against a stale count and release the barrier early.

```python
collector_state.set_expected_count(len(nodes))   # BEFORE publishing
for node in nodes:
    await runtime.publish_message(PCMessage(content=json.dumps(node)), ...)
extracted = await collector_state.wait_for_results(timeout=300)
```

**Soft-fail:** the extractor never raises; on error it publishes an error payload so the
counter still advances and the barrier cannot deadlock.

### 2.2 Orchestrator / Worker (Phase 2 — generation)
A single `OrchestratorAgent` owns the plan and calls stateless workers in order, threading
prior results as context.

```python
@message_handler
async def handle_task(self, message: UserTask, ctx) -> FinalResult:
    generated = []
    for node in message.task["nodes"]:
        r = await self.send_message(WorkerTask(task=json.dumps(node),
                                               previous_results=generated),
                                    AgentId("pyspark_generation", "default"))
        generated.append(clean_content(r.result))
    ...
    return FinalResult(result={...})
```

---

## 3. Message & topic contracts

Topics are plain string constants (`app/communication/pyspark_topics.py`); messages are
dataclasses (`app/communication/pyspark_types.py`). Keeping these in a dedicated layer means
agents depend on **contracts, not each other** — you can swap an agent without touching its
peers.

| Message | Direction | Purpose |
|---------|-----------|---------|
| `PCMessage` | publish → extractor | one canonical node to normalize |
| `PCFlowExtractionResponse` | publish → collector | normalized node (or error) |
| `UserTask` | send → orchestrator | full job (nodes + meta) |
| `WorkerTask` / `WorkerTaskResult` | send ↔ worker | one generation step |
| `FinalResult` | return ← orchestrator | assembled output |

---

## 4. Prompt engineering — the methods

Below are the major prompt-optimization techniques, what each is good for, whether this
project uses it, and **why**. The agents live in `app/prompt_engineering/prompts/`.

### 4.1 Zero-shot prompting
Just instructions, no examples. *Cheapest, lowest steering.*
**Used? Partially.** The Review agent is largely zero-shot because the task is a rubric
check, not a format-imitation task.

### 4.2 Few-shot prompting (used ✅)
Include 1–N worked examples to anchor the output format and edge handling.
**Why here:** the extractor and generator must emit a *very specific* JSON shape and a
DataFrame-variable threading convention. A single curated exemplar (1-shot) locks the format
without the cost/overfitting risk of many shots.

```text
### Few-shot exemplar
INPUT:  {... Aggregator node ...}
OUTPUT: {"node_name":"agg_DailyTotals", ... "group_by":["Cust_Id"] ...}
```

### 4.3 Output-contract / schema-first prompting (used ✅)
Pin an exact JSON schema with fixed key order and "no markdown, no prose".
**Why here:** the orchestrator parses every response with `json.loads`. A strict contract
makes the LLM output machine-actionable and lets `clean_content()` strip stray fences safely.

### 4.4 Role / persona priming (used ✅)
Open with an expert identity ("You are a principal data engineer specialized in migrating
PowerCenter to PySpark"). Activates the right domain priors.

### 4.5 Delimiters / structured sections (used ✅)
`###` headers separate Input / Task / Output contract / Constraints / Examples. Reduces
"instruction bleed" where the model confuses examples for data.

### 4.6 Chain-of-Thought, then suppress (used ✅)
Ask the model to "reason step by step **internally** and emit only the JSON". You get the
accuracy benefit of deliberate reasoning without leaking thoughts into a JSON payload that
must parse.

```text
### Reasoning policy
Reason about column lineage INTERNALLY; emit ONLY the final JSON.
```

### 4.7 Decision-table / rubric prompting (used ✅)
Give the model an explicit lookup table instead of prose rules. The generator's
PowerCenter→PySpark rubric and the Iceberg writer's update-strategy→write-mode table are
examples. Tables are compact, unambiguous, and reproducible.

### 4.8 Context injection / retrieval-style grounding (used ✅)
The generator receives previously generated fragments as `previous_results` so it references
the correct upstream DataFrame variable. This is lightweight RAG: ground each step in just
the relevant prior context, not the whole mapping.

### 4.9 Negative constraints + guardrails (used ✅)
Explicit "NEVER rewrite the SQL override; copy it byte-for-byte." Hallucinated SQL rewrites
are the #1 parity risk in this migration, so the guardrail is repeated in extractor,
generator, and reviewer prompts (defense in depth).

### 4.10 Self-verification / self-check (used ✅)
End the prompt with a checklist the model must satisfy ("Are all 12 keys present? Is the SQL
byte-identical? Is the JSON parseable?"). Cheap accuracy boost without a second model call.

### 4.11 LLM-as-a-judge (used ✅)
The Review agent is an adversarial judge with a constrained label set
(`pass | warn | fail`). Separating generation from evaluation catches lineage/parity defects
the generator is blind to.

### 4.12 Prompt chaining / task decomposition (used ✅)
The whole pipeline is one big task split into small prompts: extract → generate (per node) →
write → review. Small, single-responsibility prompts are more accurate and debuggable than
one mega-prompt, and they map cleanly onto the agent topology.

### 4.13 Decoding determinism (used ✅, model-aware)
For the gpt-4o family we set `temperature=0` + `seed=8350` for reproducible output. The
gpt-5 family (this deployment, `gpt-5-mini`) only supports the default temperature, so
`app/config/azure_openai.py` **omits those knobs automatically** and we lean on the prompt
guardrails ("be deterministic", verbatim SQL, fixed schema) instead.

### 4.14 Techniques deliberately *not* used (and why)
- **Self-consistency (sample N, vote):** N× cost; our determinism + judge pattern is cheaper
  for code generation.
- **ReAct / tool-calling loops:** the work is a fixed pipeline, not open-ended search, so a
  static orchestration is simpler and more predictable.
- **Automatic prompt optimization (DSPy / APE):** valuable at scale, but overkill for a
  curated 4-prompt system; the hand-tuned prompts are auditable for a resume artifact.

---

## 5. How the techniques map to each agent

| Agent | Primary techniques |
|-------|--------------------|
| `PCExtractorAgent` | role priming, schema-first, 1-shot, CoT-suppressed, verbatim-SQL guardrail, self-check |
| `PySparkGenerationAgent` | role priming, rubric table, context injection, 1-shot, schema-first, determinism |
| `IcebergWriterAgent` | decision-table, schema-first, 1-shot, audit-column guardrail |
| `ReviewAgent` | LLM-as-judge, rubric checklist, constrained labels, schema-first |

---

## 6. End-to-end data flow recap

```text
XML → pre_process_shared_folder → canonical nodes
   → [publish] PCExtractorAgent → [publish] PCResultCollectorAgent (barrier)
   → [send] OrchestratorAgent → PySparkGenerationAgent (per node)
                              → IcebergWriterAgent
                              → ReviewAgent
   → FinalResult { pyspark_nodes, iceberg_write, review }
```

See `docs/architecture-diagrams.md` for the mermaid sequence diagrams.
