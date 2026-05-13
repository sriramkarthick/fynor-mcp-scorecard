"""
fynor test suite.

Run with: pytest

Test organisation mirrors the package structure:
  tests/checks/mcp/      — one test file per check
  tests/adapters/        — adapter unit tests
  tests/intelligence/    — pattern detector tests
  tests/test_scorer.py   — scorer unit tests
  tests/test_history.py  — history append/read tests

All check tests use a MockAdapter that returns controlled responses,
so tests never make real network calls.
"""
