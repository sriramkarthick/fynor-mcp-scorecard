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

from fynor import __version__


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
    from fynor.history import append_result
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
        click.echo(json.dumps(dataclasses.asdict(scorecard), indent=2))
        return

    # Terminal output
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

    for r in results:
        if r.result == "na":
            status = "-"
            score_str = " N/A"
        else:
            status = "✓" if r.passed else "✗"
            score_str = f"{r.score:3d}"
        click.echo(f"  {status} {r.check.ljust(22)} {score_str}  {r.detail[:60]}")

    click.echo("─" * 60)

    if scorecard.grade in ("A", "B"):
        click.echo(
            f"\n  Agent-Ready candidate (grade {scorecard.grade}). "
            "30 consecutive passing days → earn the certification badge."
        )
    else:
        click.echo(f"\n  {scorecard.summary}")

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
