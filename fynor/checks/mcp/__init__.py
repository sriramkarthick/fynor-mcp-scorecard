"""
Fynor MCP Checks
Reliability checks for MCP servers under agent-specific load patterns.
"""

CHECKS = [
    "response_time",
    "error_rate", 
    "schema_validation",
    "retry_behavior",
    "auth_token_handling",
    "rate_limit_compliance",
    "timeout_handling",
    "log_completeness",
]

VERSION = "0.0.1-dev"
