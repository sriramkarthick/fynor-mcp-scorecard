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

import sys
import click

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
def check(target: str, interface_type: str, auth_token: str | None, output: str) -> None:
    """
    Run all reliability checks against an interface.

    Writes results to ~/.fynor/history.jsonl for pattern detection.

    Example:
      fynor check --target http://localhost:8000/mcp --type mcp
    """
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

    results = []
    for check_fn in checks:
        with click.progressbar(
            length=1,
            label=f"  {check_fn.__name__.replace('check_', '').ljust(20)}",
        ) as bar:
            result = check_fn(adapter)
            bar.update(1)
            results.append(result)
            append_result(target, interface_type, result)

    scorecard = score(target, interface_type, results)

    if output == "json":
        import json, dataclasses
        click.echo(json.dumps(dataclasses.asdict(scorecard), indent=2))
        return

    # Terminal output
    click.echo()
    click.echo("─" * 60)
    click.echo(f"  Target:    {target}")
    click.echo(f"  Type:      {interface_type.upper()}")
    click.echo(f"  Grade:     {scorecard.grade}  ({scorecard.weighted_score:.1f}/100)")
    if scorecard.security_capped:
        click.echo("  ⚠  ADR-02 security cap applied (critical security failure)")
    click.echo()
    click.echo(f"  Security:    {scorecard.security_score:.1f}/100")
    click.echo(f"  Reliability: {scorecard.reliability_score:.1f}/100")
    click.echo(f"  Performance: {scorecard.performance_score:.1f}/100")
    click.echo()

    for r in results:
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
