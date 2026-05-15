# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x (current) | Yes |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email **sriram@fynor.tech** with:

1. A clear description of the vulnerability
2. Steps to reproduce (target URL, command, output)
3. Potential impact — what can an attacker do?
4. Your suggested fix, if you have one

You will receive an acknowledgement within **48 hours** and a status update within **7 days**.

## Scope

In scope:
- SSRF bypass via `--target` parameter
- Auth token leakage via history log (`~/.fynor/history.jsonl`)
- Remote code execution via malicious server responses
- Credential exposure in CLI output or JSON output

Out of scope:
- Denial-of-service against third-party targets (use `--skip-ssrf-check` responsibly)
- Issues in third-party dependencies (report to the dependency's maintainers)

## Disclosure Policy

Once a fix is merged and released, we will publish a brief advisory in `CHANGELOG.md`. We credit reporters by name unless they request anonymity.
