# infra/cloudflare/outputs.tf — Outputs from Cloudflare Terraform module

output "api_subdomain" {
  description = "Fully-qualified domain name for the Fynor API endpoint."
  value       = "api.fynor.tech"
}

output "rate_limit_ruleset_id" {
  description = "Cloudflare Ruleset ID for the rate limiting rules."
  value       = cloudflare_ruleset.fynor_rate_limit.id
}

output "waf_ruleset_id" {
  description = "Cloudflare Ruleset ID for the WAF custom rules."
  value       = cloudflare_ruleset.fynor_waf.id
}

output "cloudflare_proxy_status" {
  description = "Reminder: DNS record must be proxied for rate limiting to apply."
  value       = "PROXIED — Cloudflare is active in front of Railway. Rate limiting enabled."
}
