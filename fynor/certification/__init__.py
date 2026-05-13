"""
fynor.certification — Agent-Ready Certification layer.

An MCP server, REST API, or other interface that passes all checks for
30 consecutive days earns the "Fynor Agent-Ready" badge.

The badge links to fynor.tech/cert/{target_id} — a live public certificate.
Developers embed it in their README:

  [![Agent-Ready](https://fynor.tech/badge/{target_id})](https://fynor.tech/cert/{target_id})

Why certification matters:
  The badge is distribution. Every interface that earns Agent-Ready
  links back to Fynor. Every developer who sees it clicks through.
  The certification is how "Software for Agents" becomes a market position,
  not just a product feature.

Build sequence:
  Month 6   — Certificate data model (this module)
  Month 12  — Badge issuance API (fynor.tech/cert)
  Month 12  — Badge renderer (SVG, shield.io-compatible)
  Month 20  — Certification marketplace (v1.0)
"""

from fynor.certification.certificate import Certificate, CertificationStatus

__all__ = ["Certificate", "CertificationStatus"]
