---
tags: [concept, python, lld]
created: 2026-10-08
up: "[[Home]]"
related: "[[Chunking]]"
---
# Python Concepts in `parsers.py`

Every concept you must be able to defend line-by-line, mapped to the real file.
**Runnable proofs:** `interview/python-concepts-parsers.ipynb` (executes against this code).
**Drill context:** `interview/lld-extensible-document-parser.md` (spoken LLD, trace in progress).

## 1. `from __future__ import annotations` (line 14)
Makes **every annotation a string**, evaluated lazily. Buys you: forward references
(`list[Block]` before/inside definitions) and no runtime cost for importing the module.
*Say this:* "It postpones annotation evaluation, so annotations never run at import time and
forward references work. On 3.14 (PEP 649) it's effectively redundant, but harmless and
keeps 3.9+ compatibility."

## 2. `class BlockKind(str, Enum)` (line 25)
The `str` mixin makes members behave like strings: `BlockKind.TABLE == "table"` is True,
it JSON-serialises and logs cleanly. **Mixin first** in the MRO.
*Say this:* "I used `str, Enum` so the values interop with Pydantic/JSON without `.value`
plumbing; on 3.11+ I'd write `StrEnum`."

## 3. `@dataclass(slots=True)` (line 31)
Auto-generates `__init__`/`__repr__`/`__eq__`. `slots=True` adds `__slots__`:
less memory per instance (no `__dict__`), faster attribute access, and **typo-proof** —
`b.texxt = 1` raises `AttributeError` instead of silently creating a field.
Costs: no dynamic attributes; be careful with inheritance + defaults.

## 4. `field(default_factory=list)` (lines 38-39)
The classic trap: `section_path: list[str] = []` would be **one shared list across every
instance**. `default_factory` calls `list()` per instance.
*Proof:* notebook cell 1 shows two `Block`s polluting each other without it.

## 5. `@property` (lines 41-43, 51-57)
Computed, read-only attributes (`is_table`, `table_count`, `total_table_rows`) — derived
state lives in one place instead of being stored and going stale.
*Follow-up you'll get:* "why not cache it?" → `functools.cached_property` (needs `__dict__`, so
it's incompatible with `slots=True` without adding `__dict__` back).

## 6. `typing.Protocol` (lines 60-63)
The Strategy seam, **structurally typed**: `MarkdownParser` never inherits from it yet
satisfies it. No coupling between implementations and the interface, and tests can pass any
duck-typed stub. `...` (Ellipsis) is the no-op method body.
*Say this:* "Protocol = duck typing with static checking. An ABC would force inheritance and
couple every parser to a base class; `@runtime_checkable` is only needed if I want `isinstance`."

## 7. Registry dispatch (lines 295-305)
`_PARSERS: dict[DocumentFormat, type]` keyed by enum + `get_parser()` returning an instance
= **Open/Closed**: a new format is a new file plus one registration line, with zero edits to
existing code, and no shared class to merge-conflict on.
**The honest wart:** `type` is too broad for mypy, hence `# type: ignore[return-value]`. The
proper fix is `dict[DocumentFormat, type[DocumentParser]]` — say that out loud; it shows you
read the error instead of silencing it. (Alternative seam: `functools.singledispatch`, but that
dispatches on *type of argument*, and our key is a format **value**.)

## 8. Regex idioms
- `re.compile(r"^(#{1,6})\s+(.*)$")` (line 70): compiled at module scope (compiled once,
  thread-safe, and reads as declarative config). `^...$` anchors the line; groups extract
  level + text.
- `match` vs `search` vs `fullmatch`: line 108 uses `match` (must start at position 0 — correct
  for "this line is a heading"), line 121 uses `fullmatch` for the whole-string separator test
  `\|?[\s:\-|]+\|?`.
- `re.sub(r"\s+", " ", text).strip()` (line 164): the canonical whitespace-collapse idiom.
- `re.split(r"\n\s*\n", source)` (line 288): blank-line split that tolerates whitespace-only
  lines.
*Interview:* mention backtracking risk with nested quantifiers; prefer explicit anchors; the
`re` module caches compiled patterns but `re.compile` at module scope documents intent.

## 9. Subclassing `html.parser.HTMLParser` (line 142)
An event-driven (SAX-like) parser: you implement `handle_starttag` / `handle_endtag` /
`handle_data`, drive it with `feed()` + `close()`, and **keep the state machine yourself**
(`_in_table` counter, `_skip_depth`, `_buf`, `_cell`, `_capture_text`).
- `super().__init__(convert_charrefs=True)` (line 150): auto-decodes `&amp;` → `&`.
- `super().close()` after flushing (line 258) or buffered text is lost.
- Depth counters instead of booleans: `_in_table += 1` handles **nested tables**, `max(0, ...)`
  clamps on stray end tags (lines 196, 212).
*Trade-off to state:* stdlib HTMLParser is **not** a spec-compliant HTML5 parser — no error
recovery/auto-closing like lxml/html5lib/bs4. Justified here because SEC filings are
machine-generated and regular, and it removes a heavyweight dependency; the mitigation is
routing genuinely broken HTML to an lxml strategy behind the same interface.

## 10. Buffers, joins and hierarchy bookkeeping
- `" ".join(self._buf)` + `re.sub` + `.strip()` then `self._buf = []` — list-of-strings +
  join avoids O(n^2) string concatenation in a loop.
- Section path: `self._section_path[: level - 1] + [text]` (line 227) keeps a stack semantics:
  a heading at depth *d* truncates everything deeper and appends itself. Be ready to step
  through `h1 → h2 → h1`.
- `list(self._section_path)` copies the path into each Block — otherwise every block would
  alias one mutable list.

## 11. Filtering + mutation after construction (lines 269-275)
`[b for b in blocks if not (b.is_table and len(b.table_rows or []) < 2)]` drops 1-row
layout tables (the `or []` guards `None`). Then `b.text = ...` mutates blocks post-parse to
serialise tables as markdown — legal because the dataclass isn't `frozen`, and it keeps one
representation searchable while `table_rows` stays structured.
*Interview:* "mutable dataclass because the parse pass post-processes blocks; frozen would
force a second constructor pass."

## Quiz (answer out loud, then check the notebook)
1. What breaks with `section_path: list[str] = []`, and how does `default_factory` fix it?
2. Why `str, Enum` rather than plain `Enum`? What is `StrEnum`?
3. `match` vs `search` vs `fullmatch` — which does line 108 want, and why?
4. Why `type[DocumentParser]` instead of `type` in the registry annotation?
5. `Protocol` vs `ABC` — when do you need `@runtime_checkable`?
6. Why `super().__init__(convert_charrefs=True)` and why call `super().close()`?
7. What does `slots=True` buy you, and what does it cost?
8. Why a **depth counter** for tables instead of a boolean?
9. Why `list(section_path)` when constructing each Block?
10. What's the honest limitation of stdlib `HTMLParser` for this job, and your mitigation?

## 12. When to use `slots=True` — decision guide

**Use it when:**
- **Many instances** (thousands to millions): every plain dataclass instance carries a `__dict__`
  plus its keys. Blocks/chunks/spans/points/DTOs in a hot path are the classic case.
- **Fixed, known schema** — record-like classes, which is exactly what parser output is.
- You want **typo-proofing** (no silent `obj.texxt = 1`) and slightly faster attribute access.
- You want less GC pressure: no per-object dict to allocate, traverse and collect.

**Skip it when:**
- You need **dynamic attributes** — `setattr(obj, name, value)` from config, plugins, monkey-patching.
- You need **`functools.cached_property`** (it requires `__dict__` to store the cache).
- You need **`weakref`** — slotted classes reject it unless you pass `weakref_slot=True` (3.11+).
- A base class has no `__slots__` (instances get `__dict__` back, so you lose the benefit), or you
  combine multiple slotted bases with conflicting layouts.
- The class has a handful of instances — no measurable win, only constraints.

**Measured in this repo — and the two methods disagree, so know both:**
- `sys.getsizeof(obj) + sys.getsizeof(obj.__dict__)`: 344 B → 56 B (**288 B/obj**) — counts the object and
  its dict as separate blocks, which is how the overhead *feels* when reasoning per record.
- `tracemalloc` over 100,000 live instances: 168 B → 128 B (**≈40 B/obj**, ≈40 MB per 1M) — real heap
  allocation; PEP 412 key-sharing dicts are cheaper than `getsizeof` implies, and interned strings are
  shared either way.
- **The dependable rule:** you save one `__dict__` per instance — roughly 100-250 B depending on field
  count — so at 1M blocks that is tens to hundreds of MB *plus* GC scan time. Order of magnitude, not a
  precise constant: **say "an order of tens to hundreds of MB per million records"**, not a fake exact number.

**Applied to your code:** `Block`, `Chunk` and `ParsedDocument` use `slots=True` — correct call, since
one 10-K already yields 239 chunks and one batch yielded 290 points; the corpus is the multiplier.
One consequence to know: `ParsedDocument.table_count` / `total_table_rows` recompute the sum on every
access and **cannot use `cached_property`** under slots — if that ever gets hot, cache it as a field.

**Related knobs:** `slots=True` (3.10+), `weakref_slot=True` (3.11+), `frozen=True` combines fine
(immutable record), and for maximum density `NamedTuple`/`msgspec` beat both.
