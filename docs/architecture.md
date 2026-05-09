# Fynor Architecture

## Structure
fynor/
├── cli.py # CLI entry point
├── checks/
│ ├── mcp/ # MCP server checks
│ ├── rest/ # REST API checks
│ ├── graphql/ # GraphQL checks
│ ├── grpc/ # gRPC checks
│ ├── websocket/ # WebSocket checks
│ ├── soap/ # SOAP checks
│ ├── security/ # Cross-cutting security
│ └── cli_tool/ # CLI tool checks
├── report/ # Report generation
└── ontology/ # Domain correctness rules


## Design principle

Every check module follows the same interface:
- Input: target URL or endpoint
- Output: pass/fail with specific failure reason
- Side effect: none (read-only audit)
