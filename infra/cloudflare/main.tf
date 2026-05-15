# infra/cloudflare/main.tf — Cloudflare rate limiting for Fynor
#
# Decision D4 (plan-eng-review 2026-05-15):
#   Cloudflare is the PRIMARY rate limiter, running before traffic reaches Railway.
#   DynamoDB rate limiting is SECONDARY (fallback only).
#
# Threat this mitigates:
#   If the DynamoDB rate-limit table is unavailable (overloaded or under attack),
#   a "fail open" secondary-only design gives attackers unlimited access to
#   POST /check. Cloudflare blocks the flood before it reaches Railway,
#   independent of DynamoDB availability.
#
# Free tier sufficiency:
#   Cloudflare's free zone plan includes Rate Limiting (as of 2024 WAF rewrite).
#   100 req/30s per IP = ~200 req/min — sufficient for Phase A demand probe.
#   Enterprise plan required only if custom response bodies or analytics needed.
#
# Terraform provider: hashicorp/cloudflare >= 4.0
# Docs: https://registry.terraform.io/providers/cloudflare/cloudflare/latest

terraform {
  required_version = ">= 1.5"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ---------------------------------------------------------------------------
# Rate limit ruleset — applied at zone level, phase: http_ratelimit
# ---------------------------------------------------------------------------

resource "cloudflare_ruleset" "fynor_rate_limit" {
  zone_id     = var.cloudflare_zone_id
  name        = "Fynor — Rate Limit Rules"
  description = "Primary rate limiting for fynor.tech API (D4 — 2026-05-15)"
  kind        = "zone"
  phase       = "http_ratelimit"

  # Rule 1: POST /check — the expensive endpoint (fires a full check pipeline)
  rules {
    action      = "block"
    description = "POST /check: 100 req/30s per IP (D4 primary limiter)"
    enabled     = true

    # Match: any POST to any path containing /check
    expression = "(http.request.method eq \"POST\" and http.request.uri.path contains \"/check\")"

    ratelimit {
      # Count by source IP — protects against unauthenticated floods
      characteristics = ["ip.src"]

      # Window: 30 seconds
      period = 30

      # Threshold: 100 requests per window per IP
      # At 1 check/sec per user, this allows 100 concurrent checks per IP —
      # more than any legitimate user would need.
      requests_per_period = 100

      # Block duration: 60 seconds after the threshold is crossed
      # Long enough to deter repeat floods, short enough not to punish
      # legitimate bursty CI/CD pipelines.
      mitigation_timeout = 60
    }
  }

  # Rule 2: All API endpoints — backstop against general API abuse
  rules {
    action      = "block"
    description = "All API paths: 500 req/60s per IP (backstop)"
    enabled     = true

    expression = "http.request.uri.path starts_with \"/api/\""

    ratelimit {
      characteristics         = ["ip.src"]
      period                  = 60
      requests_per_period     = 500
      mitigation_timeout      = 120
    }
  }

  # Rule 3: Badge endpoint — higher limit (CDN-cached, but protect origin)
  rules {
    action      = "block"
    description = "Badge endpoint: 1000 req/60s per IP (CDN miss protection)"
    enabled     = true

    expression = "http.request.uri.path starts_with \"/badge/\""

    ratelimit {
      characteristics         = ["ip.src"]
      period                  = 60
      requests_per_period     = 1000
      mitigation_timeout      = 60
    }
  }
}

# ---------------------------------------------------------------------------
# Security rule: block known bad bots and empty User-Agent
# ---------------------------------------------------------------------------

resource "cloudflare_ruleset" "fynor_waf" {
  zone_id     = var.cloudflare_zone_id
  name        = "Fynor — WAF Rules"
  description = "Block obvious abuse before rate limiting applies"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules {
    action      = "block"
    description = "Block requests with empty User-Agent to POST /check"
    enabled     = true

    # Legitimate fynor CLI and web tool always send a User-Agent.
    # Empty UA = scripted attack or misconfigured client.
    expression = "(http.request.method eq \"POST\" and http.request.uri.path contains \"/check\" and http.user_agent eq \"\")"
  }
}

# ---------------------------------------------------------------------------
# DNS record — point fynor.tech to Railway (Phase A)
# Replace Railway URL with ECS load balancer in Phase B
# ---------------------------------------------------------------------------

resource "cloudflare_record" "fynor_api" {
  zone_id = var.cloudflare_zone_id
  name    = "api"            # api.fynor.tech
  type    = "CNAME"
  value   = var.railway_cname
  proxied = true             # MUST be true — enables Cloudflare rate limiting

  comment = "Phase A: Railway backend. Replace with ALB in Phase B (Month 4-5)."
}

resource "cloudflare_record" "fynor_apex" {
  zone_id = var.cloudflare_zone_id
  name    = "@"              # fynor.tech (landing page)
  type    = "CNAME"
  value   = var.landing_page_cname
  proxied = true

  comment = "Landing page (S3 + CloudFront). Independent of API backend."
}
