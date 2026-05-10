# Technology Stack — Every Decision + Reason

## Core Language
Python 3.11+
Reason: dominant language in AI/DevOps tooling ecosystem;
        httpx, grpcio, gql, websockets, mcp SDK all first-class Python;
        pip install fynor is the natural distribution for developer tools

## Protocol Libraries — One Per Interface Type Audited

| Library        | Interface   | Why this one                                      |
|----------------|-------------|---------------------------------------------------|
| httpx          | REST + MCP  | async-first; NOT requests (needs async for Phase C)|
| gql            | GraphQL     | introspection support; maintained; type-safe       |
| grpcio+protobuf| gRPC        | official Google library; reflection API built-in   |
| websockets     | WebSocket   | async; ping/pong control; reconnect support        |
| zeep           | SOAP        | WSDL parsing; fault envelope handling              |
| mcp (SDK)      | MCP         | official Anthropic MCP Python SDK                  |
| subprocess+pty | CLI tools   | runs any CLI binary; captures exit codes + stdout  |

CRITICAL: Use httpx, NEVER requests.
Reason: requests is synchronous only; Phase C runs checks in parallel;
        async httpx enables concurrent audits without blocking.

## CLI + Output Framework

| Library | Role           | Why                                                  |
|---------|----------------|------------------------------------------------------|
| click   | CLI framework  | fynor run / fynor audit / fynor report commands      |
| rich    | Terminal output| tables, progress bars, color scores — developer UX   |
| typer   | Optional v1.0  | upgrade from click if type-safe CLI needed at scale  |

## REST API (Phase B v1, Month 9)
FastAPI 0.111+
Reason: NOT Flask.
- Auto-generates OpenAPI docs (enterprise buyers demand this)
- Native async support (same event loop as httpx checks)
- Pydantic models = automatic request validation
- Production-grade performance

## Data Layer

| Technology       | Role                          | Phase | Why                                         |
|------------------|-------------------------------|-------|---------------------------------------------|
| PostgreSQL 16    | Primary DB (ground truth moat)| B v1  | pgvector extension for Phase C              |
| SQLAlchemy 2.0   | ORM                           | B v1  | async support; migrations via Alembic       |
| Alembic 1.13     | Schema migrations             | B v1  | versioned, reversible migrations            |
| Redis 7          | Cache + sessions              | B v1  | cache last 24h check results; rate limiting |
| pgvector 0.7     | Vector similarity search      | C     | similarity search on ground truth labels    |
| Anthropic SDK    | Embeddings + domain eval      | C     | generate embeddings for ground truth records|

PostgreSQL NOT MySQL:
Reason: pgvector extension is PostgreSQL-only; Phase C similarity search requires it.

## Phase B Hosting Stack (ADR-03 — hosted from day one)

| Layer    | Service          | Cost        | Why                                          |
|----------|------------------|-------------|----------------------------------------------|
| Frontend | Vercel (Next.js) | $0 free     | instant deploy; Hobby tier handles 20 users  |
| Backend  | Railway          | $5-7/month  | zero-config FastAPI deploy; auto-scaling      |
| Database | Supabase         | $0 free     | managed PostgreSQL; RLS built-in; dashboard  |
| DNS/CDN  | Cloudflare       | $0 free     | fynor.dev DNS; DDoS protection               |
| Auth     | Clerk            | $0 free     | GitHub OAuth; enterprise SSO at Phase C      |
| Billing  | Stripe           | 2.9%+$0.30  | $49/month managed; $5K+ enterprise invoices  |

Total Phase B cost: $5-7/month
Revenue at 20 managed users x $49: $980/month
Margin: 99%

Supabase NOT Neon:
Reason: Supabase includes connection pooling + RLS + dashboard on free tier.
        Neon requires paid plan for connection pooling.

Railway NOT Heroku:
Reason: Heroku removed free tier; Railway has $5/month entry; same DX.

## Phase C Infrastructure — AWS

Migrate from Railway/Supabase to AWS when Phase C has first enterprise client.

| Service              | Role                          | Spec                              |
|----------------------|-------------------------------|-----------------------------------|
| ECS Fargate          | API + check runner containers | 2 tasks min; scales to 10         |
| RDS PostgreSQL       | Ground truth DB               | Multi-AZ, encrypted, automated backups|
| ElastiCache Redis    | Cache cluster                 | cluster mode; <1ms latency        |
| S3                   | Reports, evidence, ontologies | versioned; encrypted              |
| CloudFront           | CDN for dashboard             | <50ms global report load          |
| Route 53             | DNS                           | fynor.dev + api.fynor.dev         |
| Terraform            | All infrastructure as code    | reproducible; acquirer-ready audit|

Cost: $200-800/month at 20 enterprise clients.
Terraform manages ALL of it — critical for acquisition due diligence.

Per-enterprise isolation (Phase C migration path from ADR-04):
- Dedicated RDS instance per client who demands it
- VPC peering to their AWS account
- Client subdomain: client_acme.fynor.dev

## Frontend Stack (Phase B v1, Month 9)

| Library    | Role              |
|------------|-------------------|
| Next.js 14 | React framework   |
| Tailwind 3 | Styling           |
| Recharts   | Score trend charts|
| Clerk      | Auth (GitHub OAuth)|
| Vercel     | Hosting           |

## Package Distribution

| Channel          | Command              | Ships    | Trigger         |
|------------------|----------------------|----------|-----------------|
| PyPI             | pip install fynor    | Month 6  | primary channel |
| GitHub Action    | uses: fynor/check@v1 | Month 8  | CI/CD market    |
| npm              | npx fynor            | Month 15 | community demand|
| Docker           | docker run fynor     | Month 15 | enterprise demand|

## CI/CD (GitHub Actions)

ci.yml:
  Trigger: every push, every PR
  Steps: checkout -> setup Python 3.11 -> pip install -e ".[dev]" -> pytest -v

publish.yml:
  Trigger: git tag push (v0.1, v0.2, etc.)
  Steps: build -> publish to PyPI via Trusted Publisher (no API key needed)

## Observability (Phase C)

| Tool           | Role                                    |
|----------------|-----------------------------------------|
| OpenTelemetry  | Instrument Fynor itself (traces, spans) |
| Prometheus     | /metrics endpoint for enterprise buyers |
| structlog      | Structured JSON logs                    |
| Grafana        | Dashboards for enterprise client portals|

## Key Decision Summary

| Decision         | Chosen       | Rejected      | Reason for rejection                      |
|------------------|--------------|---------------|-------------------------------------------|
| HTTP library     | httpx        | requests      | requests is sync-only; breaks Phase C     |
| API framework    | FastAPI      | Flask         | Flask has no async; no auto OpenAPI docs  |
| Primary DB       | PostgreSQL   | MySQL         | pgvector is PostgreSQL-only               |
| Frontend hosting | Vercel       | Heroku        | Heroku removed free tier                  |
| DB hosting (B)   | Supabase     | Neon          | Neon needs paid plan for pooling          |
| Multi-tenancy    | RLS then/DB  | DB from day 1 | too expensive early; RLS starts cheap     |
| MCP server       | Month 12     | Month 6       | differentiator deserves polish (ADR-05)   |
| Language         | Python       | Node.js       | AI/DevOps tooling is Python-dominant      |
