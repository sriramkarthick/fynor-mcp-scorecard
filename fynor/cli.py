"""
fynor CLI — entry point for all check commands.

Usage:
  fynor check --target <url> --type mcp
  fynor check --target <url> --type rest
  fynor history --target <url>
  fynor patterns [--target <url>]
  fynor version
"""

from __future__ import annotations

import asyncio
import sys

import click

# Reconfigure stdout/stderr to UTF-8 on platforms where the default encoding
# is not UTF-8 (e.g. Windows cmd.exe which defaults to cp1252). Check detail
# strings contain ≤, ─, ✓, ✗ — these need UTF-8 to display correctly.
# errors="replace" ensures the CLI never crashes on an unencodable character.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import textwrap

from fynor import __version__


def _render_evidence(check: str, ev: dict) -> None:  # type: ignore[type-arg]
    """Render check-specific evidence from the client's server in a readable format."""
    if check == "latency_p95":
        latencies = ev.get("latencies_ms_sorted", [])
        if latencies:
            click.echo(f"    We sent {ev.get('probe_count', 20)} probe requests.")
            click.echo(f"    Response times (ms, sorted): {', '.join(str(x) for x in latencies)}")
            click.echo(f"    P95 = position {ev.get('p95_index', '?')+1} of {len(latencies)}: "
                       f"{ev.get('p95_ms', '?')}ms")
            click.echo(f"    Min: {ev.get('min_ms')}ms  |  Max: {ev.get('max_ms')}ms  |  "
                       f"Errors: {ev.get('error_count', 0)}")

    elif check == "error_rate":
        dist = ev.get("status_code_distribution", {})
        if dist:
            click.echo(f"    We sent {ev.get('probe_count', 50)} probe requests.")
            dist_str = "  ".join(f"HTTP {k}: {v}×" for k, v in sorted(dist.items()))
            click.echo(f"    Response distribution: {dist_str}")
        if ev.get("first_error_status"):
            click.echo(f"    First error — HTTP {ev['first_error_status']}:")
            preview = ev.get("first_error_response_preview", "")
            if preview:
                click.echo(f"      {preview[:120]}")
        if ev.get("rate_limited_count"):
            click.echo(f"    Note: {ev['rate_limited_count']} HTTP 429 responses excluded "
                       f"from error count (rate-limit, not error).")

    elif check == "auth_token":
        if ev.get("f4_ran"):
            click.echo(f"    We sent: Authorization: Bearer {ev.get('probe_token_used')}")
            click.echo(f"    Your server responded: HTTP {ev.get('f4_response_status', '?')}")
            preview = ev.get("f4_response_preview", "")
            if preview:
                click.echo(f"    Response body (first 300 chars):")
                for line in _wrap(preview, 68):
                    click.echo(f"      {line}")
        if ev.get("f2_ran") and ev.get("f2_unauth_status") is not None:
            click.echo(f"    Unauthenticated request → HTTP {ev['f2_unauth_status']}")
            if ev.get("f2_response_preview"):
                click.echo(f"      {ev['f2_response_preview'][:100]}")
        leaked = ev.get("f1_leaked_header_names", [])
        if leaked:
            click.echo(f"    Credential-pattern headers in response: {leaked}")

    elif check == "schema":
        violations = ev.get("violations", [])
        if violations:
            click.echo(f"    Violations found in your server's response:")
            for v in violations:
                click.echo(f"      • {v}")
        fields = ev.get("worst_probe_fields")
        if fields:
            click.echo(f"    Fields present in response: {list(fields.keys())}")

    elif check == "retry":
        click.echo(f"    Probe 1 (null method) → {ev.get('probe_1_result')}")
        click.echo(f"    Probe 2 (missing id)  → {ev.get('probe_2_result')}")

    elif check == "rate_limit":
        dist = ev.get("status_code_distribution", {})
        dist_str = "  ".join(f"HTTP {k}: {v}×" for k, v in sorted(dist.items()))
        click.echo(f"    Burst: {ev.get('burst_count')} requests at "
                   f"{ev.get('burst_rps')} req/s")
        click.echo(f"    Response distribution: {dist_str}")
        if ev.get("first_429_at_request"):
            click.echo(f"    First 429 at request #{ev['first_429_at_request']}")
        if "retry_after_header_present" in ev:
            present = ev["retry_after_header_present"]
            click.echo(f"    Retry-After header: {'present' if present else 'absent'}"
                       + (f" (value: {ev['retry_after_value']})" if ev.get("retry_after_value") else ""))

    elif check == "timeout":
        click.echo(f"    Timeout budget: {ev.get('timeout_budget_s')}s")
        if ev.get("hung"):
            click.echo(f"    Result: server did not respond — hard timeout after "
                       f"{ev.get('timeout_budget_s')}s")
        elif ev.get("response_latency_ms") is not None:
            click.echo(f"    Response time: {ev['response_latency_ms']}ms "
                       f"(HTTP {ev.get('response_status', 'ERR')})")

    elif check == "log_completeness":
        probed = ev.get("paths_probed", [])
        found = ev.get("found_path")
        click.echo(f"    Paths probed: {', '.join(probed)}")
        if found:
            click.echo(f"    Responding path: {found}")
            ts_fields = ev.get("timestamp_fields_found", [])
            all_fields = ev.get("all_fields_found", [])
            if ts_fields:
                click.echo(f"    Timestamp fields found: {ts_fields}")
            if all_fields:
                click.echo(f"    All fields found: {all_fields}")
            preview = ev.get("response_preview", "")
            if preview:
                click.echo(f"    Response preview: {preview[:150]}")
        else:
            click.echo("    No endpoint responded with HTTP 200.")

    elif check == "data_freshness":
        field = ev.get("timestamp_field_found")
        if field:
            click.echo(f"    Timestamp field found: '{field}'")
            click.echo(f"    Raw value from your server: {ev.get('timestamp_raw_value')}")
            click.echo(f"    Parsed as (UTC): {ev.get('timestamp_parsed_utc')}")
            click.echo(f"    Data age: {ev.get('data_age_human')} "
                       f"({ev.get('data_age_minutes')} minutes)")
        else:
            fields = ev.get("fields_found_in_response", [])
            searched = ev.get("timestamp_keys_searched", [])
            if fields:
                click.echo(f"    Fields in your response: {fields}")
                click.echo(f"    Timestamp keys we searched for: {searched}")

    elif check == "tool_description_quality":
        tools = ev.get("tools", [])
        if tools:
            click.echo(f"    {ev.get('tool_count')} tools found in tools/list:")
            for t in tools[:8]:  # cap at 8 to keep output readable
                bar = "✓" if t["score"] >= 60 else "✗"
                click.echo(f"      {bar} {t['name']}  (score {t['score']}, "
                           f"desc: {t['description_length']} chars) — {t['result']}")
                if t.get("description_preview"):
                    click.echo(f"        \"{t['description_preview']}...\"")

    elif check == "response_determinism":
        fps = ev.get("fingerprints", [])
        if fps:
            click.echo(f"    3 probe structural fingerprints:")
            for i, fp in enumerate(fps, 1):
                click.echo(f"      Probe {i}: {fp[:80]}")
            divergent = ev.get("divergent_probe_numbers", [])
            if divergent:
                click.echo(f"    Divergent probes: {divergent}")


def _wrap(text: str, width: int = 70) -> list[str]:
    """Wrap a plain-text string to the given width, preserving newlines."""
    lines: list[str] = []
    for paragraph in text.splitlines():
        if paragraph.strip():
            lines.extend(textwrap.wrap(paragraph, width=width))
        else:
            lines.append("")
    return lines


@click.group()
@click.version_option(__version__, prog_name="fynor")
def main() -> None:
    """Fynor — AI Agent Reliability Platform."""


@main.command()
@click.option(
    "--target", "-t",
    required=True,
    help="URL of the interface to check (e.g. http://localhost:8000/mcp).",
)
@click.option(
    "--type", "interface_type",
    default="mcp",
    type=click.Choice(["mcp", "rest", "graphql", "grpc", "websocket", "soap", "cli"]),
    show_default=True,
    help="Interface type to check against.",
)
@click.option(
    "--auth-token", envvar="FYNOR_AUTH_TOKEN",
    default=None,
    help="Bearer token for authenticated interfaces (or set FYNOR_AUTH_TOKEN env var).",
)
@click.option(
    "--output", "-o",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--skip-ssrf-check",
    is_flag=True,
    default=False,
    hidden=True,
    help="Skip SSRF validation (for testing against localhost only).",
)
@click.option(
    "--profile", "-p",
    default="default",
    type=click.Choice(["default", "security", "financial"]),
    show_default=True,
    help="Check profile with context-specific pass thresholds (default|security|financial).",
)
def check(
    target: str,
    interface_type: str,
    auth_token: str | None,
    output: str,
    skip_ssrf_check: bool,
    profile: str,
) -> None:
    """
    Run all reliability checks against an interface.

    Validates the target URL for safety before running any checks.
    Writes results to ~/.fynor/history.jsonl for pattern detection.

    Example:
      fynor check --target http://localhost:8000/mcp --type mcp
    """
    from fynor.adapters.base import validate_target_url

    # SSRF protection: validate before dispatching any HTTP requests
    if not skip_ssrf_check:
        try:
            validate_target_url(target)
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)

    asyncio.run(_run_check(target, interface_type, auth_token, output, profile))


async def _run_check(
    target: str,
    interface_type: str,
    auth_token: str | None,
    output: str,
    profile: str = "default",
) -> None:
    """Async implementation of the check command."""
    import asyncio as _asyncio
    from fynor.adapters.mcp import MCPAdapter
    from fynor.adapters.rest import RESTAdapter
    from fynor.checks.mcp import ALL_CHECKS as MCP_CHECKS
    from fynor.history import append_result, CheckResult
    from fynor.scorer import score

    # Build adapter
    if interface_type == "mcp":
        adapter = MCPAdapter(target, auth_token=auth_token)
        checks = MCP_CHECKS
    elif interface_type == "rest":
        adapter = RESTAdapter(target, auth_token=auth_token)
        # TODO (Month 9): replace with REST_CHECKS
        click.echo("REST checks ship in v0.2 (Month 9). Running MCP checks against REST target.")
        checks = MCP_CHECKS
    else:
        click.echo(
            f"[{interface_type.upper()}] checks ship in a future version. "
            "See the roadmap in README.md.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"\nFynor — checking {interface_type.upper()} interface: {target}\n")

    # Run all checks concurrently for speed
    check_tasks = [check_fn(adapter) for check_fn in checks]
    results = await _asyncio.gather(*check_tasks)

    # Mark MCP-only checks as N/A for non-MCP interface types.
    # schema, retry, and tool_description_quality rely on JSON-RPC 2.0
    # semantics that REST/GraphQL/gRPC targets do not expose.  Scoring them
    # as FAIL (0) distorts the grade — they must be excluded from scoring.
    if interface_type != "mcp":
        from fynor.history import CheckResult as _CheckResult
        _MCP_ONLY: frozenset[str] = frozenset({"schema", "retry", "tool_description_quality"})
        results = tuple(
            _CheckResult(
                check=r.check,
                passed=False,
                score=0,
                value=None,
                detail=(
                    "Not applicable: this check only applies to MCP (JSON-RPC 2.0) interfaces."
                ),
                result="na",
            )
            if r.check in _MCP_ONLY
            else r
            for r in results
        )

    # Apply profile-specific pass thresholds before scoring
    from fynor.profiles import get_profile, apply_profile
    active_profile = get_profile(profile)
    results = apply_profile(list(results), active_profile)

    # Write history and display results
    for result in results:
        append_result(target, interface_type, result)

    scorecard = score(target, interface_type, list(results))

    if output == "json":
        import json
        import dataclasses
        from fynor.interpretation import interpret_all
        interpretations = interpret_all(list(results))
        output_data = dataclasses.asdict(scorecard)
        # Attach interpretation to each check result in the JSON output
        output_data["check_results"] = []
        for r in results:
            row = dataclasses.asdict(r)
            interp = interpretations.get(r.check)
            if interp:
                row["impact"] = interp.impact
                row["remediation"] = interp.remediation
                if interp.reproduce:
                    row["reproduce"] = interp.reproduce
                if interp.refs:
                    row["refs"] = interp.refs
            output_data["check_results"].append(row)
        click.echo(json.dumps(output_data, indent=2))
        return

    # Terminal output
    from fynor.interpretation import interpret
    click.echo()
    click.echo("─" * 60)
    click.echo(f"  Target:    {target}")
    click.echo(f"  Type:      {interface_type.upper()}")
    click.echo(f"  Grade:     {scorecard.grade}  ({scorecard.weighted_score:.1f}/100)")
    if profile != "default":
        click.echo(f"  Profile:   {profile}")
    if scorecard.security_capped:
        click.echo("  ⚠  ADR-02 security cap applied (critical security failure)")
    click.echo()
    click.echo(f"  Security:    {scorecard.security_score:.1f}/100")
    click.echo(f"  Reliability: {scorecard.reliability_score:.1f}/100")
    click.echo(f"  Performance: {scorecard.performance_score:.1f}/100")
    click.echo()

    # Collect failing checks for expanded detail section below the summary table
    failing: list[CheckResult] = []

    for r in results:
        if r.result == "na":
            status = "-"
            score_str = " N/A"
        else:
            status = "✓" if r.passed else "✗"
            score_str = f"{r.score:3d}"
            if not r.passed:
                failing.append(r)
        click.echo(f"  {status} {r.check.ljust(22)} {score_str}  {r.detail[:60]}")

    click.echo("─" * 60)

    if scorecard.grade in ("A", "B"):
        click.echo(
            f"\n  Agent-Ready candidate (grade {scorecard.grade}). "
            "30 consecutive passing days → earn the certification badge."
        )
    else:
        click.echo(f"\n  {scorecard.summary}")

    # ── Expanded findings: evidence, impact, remediation ──────────────────
    if failing:
        click.echo()
        click.echo("─" * 60)
        click.echo("  FINDINGS — what we measured, why it matters, how to fix it")
        click.echo("─" * 60)
        for r in failing:
            interp = interpret(r)
            click.echo()
            marker = "⚠ " if r.check == "auth_token" and r.score == 0 else "✗ "
            click.echo(f"  {marker}{r.check.upper()}  (score {r.score}/100)")
            click.echo()
            click.echo(f"  WHAT WE MEASURED")
            # Wrap detail at 72 chars
            detail_lines = _wrap(r.detail, 70)
            for line in detail_lines:
                click.echo(f"    {line}")
            # Show client-specific evidence from their server's actual responses
            if r.evidence:
                ev = r.evidence
                click.echo()
                click.echo(f"  EVIDENCE FROM YOUR SERVER")
                _render_evidence(r.check, ev)

            if interp:
                click.echo()
                click.echo(f"  BUSINESS IMPACT FOR YOUR AI AGENTS")
                for line in _wrap(interp.impact, 70):
                    click.echo(f"    {line}")
                click.echo()
                click.echo(f"  HOW TO FIX")
                for line in interp.remediation.splitlines():
                    click.echo(f"    {line}")
                if interp.reproduce:
                    click.echo()
                    click.echo(f"  REPRODUCE IT YOURSELF")
                    for line in interp.reproduce.splitlines():
                        click.echo(f"    {line.replace('<TARGET_URL>', target)}")
                if interp.refs:
                    click.echo()
                    click.echo(f"  REFERENCES")
                    for ref in interp.refs:
                        click.echo(f"    {ref}")
            click.echo()
            click.echo("  " + "·" * 56)
        click.echo()

    click.echo()


@main.command()
@click.option("--target", "-t", default=None, help="Filter to a specific target URL.")
@click.option(
    "--check", "check_name",
    default=None,
    help="Filter to a specific check name.",
)
@click.option("--last", default=10, show_default=True, help="Number of most recent rows to show.")
def history(target: str | None, check_name: str | None, last: int) -> None:
    """Show check history from ~/.fynor/history.jsonl."""
    from fynor.history import read_history

    rows = read_history(target=target, check=check_name)
    if not rows:
        click.echo("No history found. Run: fynor check --target <url> --type mcp")
        return

    shown = rows[-last:]
    click.echo(f"\nShowing {len(shown)} of {len(rows)} history rows:\n")
    for row in shown:
        status = "✓" if row.get("passed") else "✗"
        click.echo(
            f"  {status}  {row.get('ts', '')[:19]}  "
            f"{row.get('type', '').ljust(10)}  "
            f"{row.get('check', '').ljust(22)}  "
            f"score={row.get('score', 0):3d}  "
            f"{str(row.get('target', ''))[:40]}"
        )
    click.echo()


@main.command()
@click.option("--target", "-t", default=None, help="Limit detection to a specific target.")
def patterns(target: str | None) -> None:
    """Run pattern detection against check history and show detected patterns."""
    from fynor.intelligence.pattern_detector import PatternDetector

    detector = PatternDetector()
    found_patterns, alerts = detector.run(target=target)

    if not found_patterns and not alerts:
        click.echo(
            "No patterns detected. "
            "Run more checks to build history — pattern detection requires 10+ runs."
        )
        return

    if alerts:
        click.echo(f"\n{len(alerts)} alert(s) detected:\n")
        for a in alerts:
            click.echo(f"  ⚠  [{a.alert_type}] {a.target}")
            click.echo(f"     {a.description}")

    if found_patterns:
        click.echo(f"\n{len(found_patterns)} pattern(s) detected:\n")
        for p in found_patterns:
            click.echo(f"  →  [{p.pattern_type}] confidence={p.confidence:.0%}")
            click.echo(f"     {p.description}")

    click.echo(
        "\nPending human review. Confirm or reject patterns in ~/.fynor/patterns.jsonl"
    )
    click.echo()
