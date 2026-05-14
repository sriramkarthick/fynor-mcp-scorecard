"""
fynor/checks/mcp/response_determinism.py — Check #11: response_determinism

Verifies the MCP server returns structurally identical responses to identical
probe requests. Non-deterministic schemas break agent reasoning chains.

Scoring:
  All 3 probes have identical key fingerprints  → score = 100
  Exactly 2 of 3 probes agree                  → score = 60  ← pass threshold
  All 3 probes have different key fingerprints  → score = 0
  Any probe fails (error / timeout)             → score = 0

ADR-03 signal class: Reliability — structural consistency
Pass threshold: score ≥ 60 (at least 2 of 3 probes structurally identical)

Note: value equality is NOT checked — only the set of keys and value types.
result.value: count of probes matching the plurality fingerprint (0–3).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

CHECK_NAME = "response_determinism"
_PROBE_COUNT = 3


def _key_fingerprint(obj: Any, depth: int = 0) -> str:
    """Canonical structural fingerprint of an object (keys + types, not values)."""
    if depth > 3:
        return type(obj).__name__
    if isinstance(obj, dict):
        parts = sorted(
            f"{k}:{_key_fingerprint(v, depth + 1)}" for k, v in obj.items()
        )
        return "{" + ",".join(parts) + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        return f"[{_key_fingerprint(obj[0], depth + 1)}]"
    return type(obj).__name__


async def check_response_determinism(adapter: BaseAdapter) -> CheckResult:
    """Send the same probe 3 times and verify structural consistency."""
    fingerprints: list[str] = []
    errors: list[str] = []

    for i in range(_PROBE_COUNT):
        try:
            response = await adapter.call()
            if response.body is None:
                errors.append(f"probe {i + 1}: empty body")
                fingerprints.append("<empty>")
            else:
                fingerprints.append(_key_fingerprint(response.body))
        except Exception as exc:
            errors.append(f"probe {i + 1}: {exc}")
            fingerprints.append("<error>")

    if errors:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=0,
            detail=f"Probe failures prevent determinism assessment: {'; '.join(errors)}.",
        )

    counts = Counter(fingerprints)
    most_common_fp, most_common_count = counts.most_common(1)[0]

    if most_common_count == 3:
        return CheckResult(
            check=CHECK_NAME, passed=True, score=100, value=3,
            detail=f"All {_PROBE_COUNT} probes returned structurally identical responses. Schema is deterministic.",
        )
    elif most_common_count == 2:
        divergent = [i + 1 for i, fp in enumerate(fingerprints) if fp != most_common_fp]
        return CheckResult(
            check=CHECK_NAME, passed=True, score=60, value=2,
            detail=(
                f"2 of {_PROBE_COUNT} probes agree; probe(s) {divergent} diverged. "
                "Minor non-determinism detected. Investigate response variance."
            ),
        )
    else:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=0,
            detail=(
                f"All {_PROBE_COUNT} probes returned different structural schemas. "
                "Server responses are non-deterministic — agents cannot reliably "
                "parse or reason over this MCP server's output."
            ),
        )
