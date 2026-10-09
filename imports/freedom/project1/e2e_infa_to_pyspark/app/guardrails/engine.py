"""Guardrails for the agentic pipeline.

Why guardrails here
-------------------
LLM agents see real source/target metadata and emit code. Two risks must be contained:
1. **Sensitive-data leakage** — PII (SSN, email, phone, credit card), secrets (API keys,
   passwords, JDBC credentials) accidentally surfacing in prompts, logs, or generated code.
2. **Unsafe / low-quality generations** — destructive SQL, prompt-injection in source
   metadata, hallucinated rewrites of SQL overrides, non-compiling code.

This module provides composable guardrails that run on **inputs** (before the LLM sees a
payload) and **outputs** (after the LLM responds). Each guardrail returns a
``GuardrailResult`` so the pipeline can redact, warn, or block.

Guardrail types implemented
---------------------------
- PIIGuardrail            : detect + redact PII (regex-based; pluggable with Presidio).
- SecretsGuardrail        : detect API keys / passwords / connection strings.
- PromptInjectionGuardrail: flag injection phrases embedded in source metadata.
- DestructiveSQLGuardrail : block DROP/TRUNCATE/DELETE-without-WHERE in generated SQL.
- SchemaGuardrail         : ensure agent output is valid JSON with required keys.
- SQLOverrideFidelityGuardrail : ensure a known SQL override is preserved verbatim.

Other guardrails worth adding in production (documented, not all implemented):
- Toxicity / content-safety (Azure AI Content Safety).
- Topical / off-domain guardrail (refuse non-migration requests).
- Token-budget / cost guardrail (truncate oversized payloads).
- Rate-limit & retry guardrail.
- Output length / loop guardrail (cap agent turns).
- Groundedness guardrail (every generated column must trace to a source column).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class GuardrailAction(str, Enum):
    ALLOW = "allow"
    REDACT = "redact"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class GuardrailResult:
    name: str
    action: GuardrailAction
    findings: List[str] = field(default_factory=list)
    sanitized_text: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.action in (GuardrailAction.ALLOW, GuardrailAction.WARN)

    @property
    def blocked(self) -> bool:
        return self.action == GuardrailAction.BLOCK


# --------------------------------------------------------------------------- #
# Individual guardrails
# --------------------------------------------------------------------------- #

_PII_PATTERNS: Dict[str, re.Pattern] = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "PHONE": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "IP": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


class PIIGuardrail:
    """Detect and redact common PII. Swap in Microsoft Presidio for production NER."""

    name = "pii"

    def __init__(self, redact: bool = True) -> None:
        self.redact = redact

    def check(self, text: str) -> GuardrailResult:
        findings: List[str] = []
        sanitized = text
        for label, pattern in _PII_PATTERNS.items():
            matches = pattern.findall(text or "")
            if matches:
                findings.append(f"{label} x{len(matches)}")
                if self.redact:
                    sanitized = pattern.sub(f"[REDACTED_{label}]", sanitized)
        if not findings:
            return GuardrailResult(self.name, GuardrailAction.ALLOW)
        action = GuardrailAction.REDACT if self.redact else GuardrailAction.WARN
        return GuardrailResult(self.name, action, findings, sanitized)


_SECRET_PATTERNS: Dict[str, re.Pattern] = {
    "PASSWORD_KV": re.compile(r"(?i)(password|pwd|passwd)\s*[=:]\s*\S+"),
    "API_KEY": re.compile(r"(?i)(api[_-]?key|secret|token)\s*[=:]\s*\S+"),
    "JDBC_CREDS": re.compile(r"(?i)jdbc:[^\s]*(user|password)=[^\s;]+"),
    "AZURE_KEY": re.compile(r"\b[A-Za-z0-9]{60,}\b"),
}


class SecretsGuardrail:
    name = "secrets"

    def check(self, text: str) -> GuardrailResult:
        findings: List[str] = []
        sanitized = text
        for label, pattern in _SECRET_PATTERNS.items():
            if pattern.search(text or ""):
                findings.append(label)
                sanitized = pattern.sub(f"[REDACTED_{label}]", sanitized)
        if not findings:
            return GuardrailResult(self.name, GuardrailAction.ALLOW)
        return GuardrailResult(self.name, GuardrailAction.REDACT, findings, sanitized)


_INJECTION_PHRASES = [
    "ignore previous instructions",
    "ignore the above",
    "disregard your instructions",
    "system prompt",
    "you are now",
    "act as",
    "reveal your prompt",
]


class PromptInjectionGuardrail:
    """Flag prompt-injection attempts hidden in source metadata / comments."""

    name = "prompt_injection"

    def check(self, text: str) -> GuardrailResult:
        low = (text or "").lower()
        hits = [p for p in _INJECTION_PHRASES if p in low]
        if hits:
            return GuardrailResult(self.name, GuardrailAction.WARN, hits)
        return GuardrailResult(self.name, GuardrailAction.ALLOW)


_DESTRUCTIVE = re.compile(
    r"(?is)\b(drop\s+table|truncate\s+table|drop\s+database)\b"
    r"|\bdelete\s+from\s+\w+\s*(;|$)(?!.*where)"
)


class DestructiveSQLGuardrail:
    """Block destructive DDL/DML in generated SQL (no WHERE-less DELETE, no DROP)."""

    name = "destructive_sql"

    def check(self, text: str) -> GuardrailResult:
        if _DESTRUCTIVE.search(text or ""):
            return GuardrailResult(
                self.name, GuardrailAction.BLOCK, ["destructive SQL detected"]
            )
        return GuardrailResult(self.name, GuardrailAction.ALLOW)


class SchemaGuardrail:
    """Ensure an agent output is valid JSON containing required keys."""

    name = "schema"

    def __init__(self, required_keys: Tuple[str, ...]) -> None:
        self.required_keys = required_keys

    def check(self, text: str) -> GuardrailResult:
        try:
            obj = json.loads(text)
        except Exception as exc:
            return GuardrailResult(
                self.name, GuardrailAction.BLOCK, [f"invalid JSON: {exc}"]
            )
        missing = [k for k in self.required_keys if k not in obj]
        if missing:
            return GuardrailResult(
                self.name, GuardrailAction.WARN, [f"missing keys: {missing}"]
            )
        return GuardrailResult(self.name, GuardrailAction.ALLOW)


class SQLOverrideFidelityGuardrail:
    """Ensure a known source SQL override is preserved verbatim in generated code."""

    name = "sql_override_fidelity"

    def __init__(self, expected_override: str) -> None:
        self.expected = (expected_override or "").strip()

    def check(self, text: str) -> GuardrailResult:
        if not self.expected:
            return GuardrailResult(self.name, GuardrailAction.ALLOW)
        # Compare on whitespace-normalized text to tolerate formatting only.
        norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
        if norm(self.expected) in norm(text):
            return GuardrailResult(self.name, GuardrailAction.ALLOW)
        return GuardrailResult(
            self.name,
            GuardrailAction.WARN,
            ["SQL override not found verbatim in output"],
        )


# --------------------------------------------------------------------------- #
# Guardrail engine
# --------------------------------------------------------------------------- #


@dataclass
class GuardrailReport:
    results: List[GuardrailResult] = field(default_factory=list)
    text: str = ""

    @property
    def blocked(self) -> bool:
        return any(r.blocked for r in self.results)

    @property
    def findings(self) -> Dict[str, List[str]]:
        return {r.name: r.findings for r in self.results if r.findings}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocked": self.blocked,
            "actions": {r.name: r.action.value for r in self.results},
            "findings": self.findings,
        }


class GuardrailEngine:
    """Run a chain of guardrails, threading redactions through the text."""

    def __init__(self, guardrails: List[Any]) -> None:
        self.guardrails = guardrails

    def run(self, text: str) -> GuardrailReport:
        report = GuardrailReport(text=text)
        current = text
        for g in self.guardrails:
            result = g.check(current)
            report.results.append(result)
            if result.sanitized_text is not None:
                current = result.sanitized_text
        report.text = current
        return report


def default_input_engine() -> GuardrailEngine:
    """Guardrails applied to data BEFORE it reaches the LLM."""
    return GuardrailEngine(
        [PIIGuardrail(redact=True), SecretsGuardrail(), PromptInjectionGuardrail()]
    )


def default_output_engine(
    required_keys: Tuple[str, ...] = ("node_name", "pyspark_code"),
) -> GuardrailEngine:
    """Guardrails applied to LLM output BEFORE it is accepted downstream."""
    return GuardrailEngine(
        [SecretsGuardrail(), DestructiveSQLGuardrail(), SchemaGuardrail(required_keys)]
    )
