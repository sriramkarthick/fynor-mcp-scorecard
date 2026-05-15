# infra/cloudflare/variables.tf — Input variables for Cloudflare Terraform module

variable "cloudflare_api_token" {
  description = "Cloudflare API token with Zone:Edit and Firewall:Edit permissions."
  type        = string
  sensitive   = true
  # Set via: export TF_VAR_cloudflare_api_token="<token>"
  # Or in CI: Cloudflare API token stored as a secret.
  # Do NOT hardcode. Do NOT commit to git.
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for fynor.tech. Found in Cloudflare dashboard → Overview."
  type        = string
  # Example: "0da42c8d2132a9ddaf714f9543ce4c0e"
}

variable "railway_cname" {
  description = <<-EOT
    Railway-assigned CNAME for the Fynor API service.
    Found in Railway dashboard → Service → Settings → Domains.
    Format: <service-name>-production-<random>.up.railway.app
    Example: "fynor-api-production-a1b2c3d4.up.railway.app"

    IMPORTANT: The Cloudflare DNS record must be PROXIED (orange cloud).
    Proxied = Cloudflare sits in front → rate limiting applies.
    DNS-only (grey cloud) = traffic bypasses Cloudflare → rate limiting disabled.
  EOT
  type        = string
}

variable "landing_page_cname" {
  description = "CNAME for the fynor.tech landing page (CloudFront or Vercel)."
  type        = string
  default     = "d1234abcd.cloudfront.net"  # Replace with actual CloudFront domain
}

variable "environment" {
  description = "Deployment environment: prod, staging, or dev."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "environment must be prod, staging, or dev."
  }
}
