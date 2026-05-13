"""
fynor.adapters — Interface adapters for the check engine.

The check engine is shared across all interface types.
Only the adapter changes per interface. This is why adding interface N
costs ~20% of the effort of the first interface — the engine never changes.

Adapter build sequence (matches version roadmap):
  v0.1  Month 6   MCPAdapter       — JSON-RPC 2.0 + MCP envelope
  v0.2  Month 9   RESTAdapter      — HTTP + JSON body
  v0.3  Month 12  GraphQLAdapter   — POST /graphql + introspection
  v0.3  Month 12  WebSocketAdapter — ws:// + heartbeat + reconnection
  v0.4  Month 15  GRPCAdapter      — gRPC + protobuf + deadline propagation
  v0.4  Month 15  SOAPAdapter      — WSDL + XML envelope + WS-Security
  v0.5  Month 18  CLIAdapter       — subprocess + exit code + stdout/stderr
"""

from fynor.adapters.base import BaseAdapter, Response

__all__ = ["BaseAdapter", "Response"]
