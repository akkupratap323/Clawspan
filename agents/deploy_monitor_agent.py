"""DeployMonitorAgent — deployment health, readiness, and rollback intelligence.

Monitors deployed services for:
  - Health status and response times
  - SSL certificate validity
  - Production readiness scoring
  - Change impact analysis
  - Rollback recommendations
  - Resource/cost efficiency
"""

from __future__ import annotations

import json
from typing import Any

from config import AWS_ACCOUNT_ID, AWS_DEFAULT_REGION, AWS_LIGHTSAIL_INSTANCE, AWS_LIGHTSAIL_IP
from core.base_agent import BaseAgent
from core.context import SessionContext
from core.profile import UserProfile
from tools.deploy_monitor import (
    check_health,
    check_port,
    check_ssl_cert,
    check_env_vars,
    check_resource_usage,
    score_readiness,
    add_service,
    remove_service,
    list_services,
    check_all_services,
    check_service_by_name,
    assess_rollback,
    estimate_deployment_cost,
    aws_status,
)
from tools.aws_monitor import (
    get_inventory_summary,
    check_instance_health,
    get_cost_summary,
    check_lightsail_network,
    get_active_alarms,
)

SYSTEM_PROMPT = """You are Clawspan's Infrastructure & Deployment Agent — the boss's DevOps brain. You monitor AWS infrastructure, check service health, score production readiness, and catch problems before users do.

YOUR ROLE:
- Monitor AWS infrastructure: Lightsail, EC2 instances, costs, CPU/memory, network
- HTTP health checks on any URL with response time + SSL validation
- Score production readiness (0-100) before/after deployments
- Detect and flag: downtime, slow responses, SSL expiry, high CPU, over-provisioning
- Recommend rollbacks when health degrades after deployment
- Track monthly AWS spend and suggest cost optimizations
- Check TCP port reachability, DNS, container health
- Proactively flag issues: "CPU spiked to 80%" or "SSL expires in 7 days"

CAPABILITIES:
AWS (real data from boto3):
- aws_status(): Full AWS inventory — all instances, CPU metrics, costs, ports
- aws_health(instance): Deep health check on specific instance
- aws_cost(): Real AWS spending from Cost Explorer (last 30 days, per-service)
- aws_network(instance): Network I/O stats (bytes in/out, 24h)

HTTP monitoring:
- deploy_health(service?): Check one or all tracked HTTP services
- deploy_readiness(url, env_vars?): Production readiness score (0-100)
- deploy_track(name, url, env?): Start tracking a URL for periodic checks
- deploy_untrack(name) / deploy_list(): Manage tracked services

Infrastructure:
- deploy_ssl(domain): SSL certificate validity + days until expiry
- deploy_port(host, port): TCP port reachability
- deploy_resources(service?): Docker container CPU/memory/status
- deploy_rollback(service): Should this service be rolled back?
- deploy_cost(): Estimated monthly cost from Docker stats

THINKING APPROACH:
- When asked "how's my infrastructure", check BOTH AWS status AND tracked HTTP services
- When CPU is < 5%, suggest downsizing to save money
- When CPU spikes > 80%, warn about scaling needs
- When SSL < 30 days, flag it. When < 7 days, mark CRITICAL
- When a service goes from healthy to down, recommend rollback with reasoning
- Connect cost advice to boss's startup: "You're spending $X but only using Y% — could save $Z/mo"
- If boss asks "is my site up", check BOTH the HTTP endpoint AND the AWS instance

RESPONSE STYLE:
- For status checks: lead with the critical finding, then details
- For cost: give actual numbers with actionable savings advice
- For readiness: score + verdict + specific issues to fix
- Always be direct about problems — boss wants truth, not sugar-coating
- For deep analysis: 4-6 sentences with numbers. For quick checks: 2-3 sentences."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "deploy_health",
            "description": "Check health of tracked services. If no service specified, checks ALL tracked services.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Specific service name to check, or empty for all",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_readiness",
            "description": "Score a deployment's production readiness (0-100). Checks health, SSL, response time, env vars, containers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Service URL to check"},
                    "env_vars": {
                        "type": "string",
                        "description": "Comma-separated required env var names (e.g. 'DATABASE_URL,REDIS_URL,API_KEY')",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_track",
            "description": "Start tracking a service for periodic health checks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Service name"},
                    "url": {"type": "string", "description": "Health endpoint URL"},
                    "env": {
                        "type": "string",
                        "enum": ["production", "staging", "canary"],
                        "description": "Environment (default: production)",
                    },
                },
                "required": ["name", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_untrack",
            "description": "Stop tracking a service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Service name to untrack"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_list",
            "description": "List all tracked services.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_ssl",
            "description": "Check SSL certificate validity and days until expiry for a domain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain name (e.g. example.com)"},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_port",
            "description": "Check if a TCP port is reachable on a host.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                },
                "required": ["host", "port"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_resources",
            "description": "Check Docker container resource usage (CPU, memory, status).",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service/container name, or empty for all",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_rollback",
            "description": "Assess whether a tracked service needs rollback based on current health.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name to assess"},
                },
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_cost",
            "description": "Estimate monthly deployment cost based on current container resource usage.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aws_status",
            "description": "Full AWS inventory — all Lightsail and EC2 instances with CPU metrics, costs, and open ports.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aws_health",
            "description": "Deep health check on a specific AWS instance (Lightsail or EC2). Shows CPU, memory, disk, ports, cost, and scaling advice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instance": {
                        "type": "string",
                        "description": "Instance name (e.g. 'my-server-1')",
                    },
                },
                "required": ["instance"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aws_cost",
            "description": "Real AWS spending from Cost Explorer — last 30 days, broken down per service.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aws_network",
            "description": "Network I/O stats (bytes in/out) for a Lightsail instance over the last 24 hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instance": {
                        "type": "string",
                        "description": "Lightsail instance name",
                    },
                },
                "required": ["instance"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aws_alarms",
            "description": "Check active Lightsail alarms — any instance in ALARM state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ── Tool handlers ─────────────────────────────────────────────────────────────

def _deploy_health(args: dict) -> str:
    service = args.get("service", "")
    if service:
        status = check_service_by_name(service)
        if status is None:
            return f"Service '{service}' not found. Use deploy_list to see tracked services."
        lines = [f"{service} ({status.url}):"]
        lines.append(f"  Status: {status.status}")
        if status.status_code:
            lines.append(f"  HTTP: {status.status_code}")
        if status.response_time_ms:
            lines.append(f"  Response: {status.response_time_ms}ms")
        if status.ssl_days_left:
            ssl_tag = "VALID" if status.ssl_valid else "INVALID"
            lines.append(f"  SSL: {ssl_tag} ({status.ssl_days_left} days)")
        if status.error:
            lines.append(f"  Error: {status.error}")
        return "\n".join(lines)
    else:
        results = check_all_services()
        if not results:
            return "No services tracked. Say 'track myservice at https://example.com' to start."

        healthy = sum(1 for r in results if r.healthy)
        degraded = sum(1 for r in results if r.degraded)
        down = sum(1 for r in results if r.is_down)

        lines = [f"Service Health ({len(results)} total):"]
        lines.append(f"  ✅ Healthy: {healthy} | ⚠️ Degraded: {degraded} | ❌ Down: {down}")
        lines.append("")

        for r in results:
            icon = "✅" if r.healthy else ("⚠️" if r.degraded else "❌")
            line = f"  {icon} {r.name}: {r.status}"
            if r.response_time_ms:
                line += f" ({r.response_time_ms}ms)"
            if r.error:
                line += f" — {r.error}"
            lines.append(line)

        return "\n".join(lines)


def _deploy_readiness(args: dict) -> str:
    url = args["url"]
    env_vars_str = args.get("env_vars", "")
    env_vars = [v.strip() for v in env_vars_str.split(",") if v.strip()] if env_vars_str else None

    result = score_readiness(url, env_vars)

    lines = [f"Production Readiness: {result['score']}/{result['max_score']}"]
    lines.append(f"Verdict: {result['verdict']}")
    lines.append(f"Status: {result['status_code']} | Response: {result['response_time_ms']}ms")
    lines.append("")
    lines.append("Checks:")
    for check_name, check_result in result["checks"].items():
        lines.append(f"  • {check_name}: {check_result}")

    if result["issues"]:
        lines.append("")
        lines.append("Issues:")
        for issue in result["issues"]:
            lines.append(f"  ⚠️ {issue}")

    return "\n".join(lines)


def _deploy_track(args: dict) -> str:
    return add_service(args["name"], args["url"], args.get("env", "production"))


def _deploy_untrack(args: dict) -> str:
    return remove_service(args["name"])


def _deploy_list(args: dict) -> str:
    return list_services()


def _deploy_ssl(args: dict) -> str:
    result = check_ssl_cert(args["domain"])
    if not result.get("valid"):
        return f"SSL for {args['domain']}: INVALID — {result.get('error', 'unknown')}"

    lines = [f"SSL Certificate for {args['domain']}:"]
    lines.append(f"  Valid: Yes")
    lines.append(f"  Days remaining: {result['days_left']}")
    lines.append(f"  Expires: {result['expires']}")
    if result.get("issuer"):
        lines.append(f"  Issuer: {result['issuer']}")
    if result.get("critical"):
        lines.append(f"  🚨 CRITICAL — expires in {result['days_left']} days!")
    elif result.get("warning"):
        lines.append(f"  ⚠️ WARNING — expires in {result['days_left']} days")
    return "\n".join(lines)


def _deploy_port(args: dict) -> str:
    result = check_port(args["host"], args["port"])
    if result.get("open"):
        return f"Port {args['port']} is OPEN on {args['host']} ({result['response_time_ms']}ms)"
    return f"Port {args['port']} is CLOSED on {args['host']}: {result.get('error', 'unreachable')}"


def _deploy_resources(args: dict) -> str:
    service = args.get("service", "")
    result = check_resource_usage(service)

    if "error" in result:
        return f"Resource check error: {result['error']}"

    if "containers" in result:
        lines = [f"Container Resources ({result['count']} container(s)):"]
        for c in result["containers"]:
            lines.append(f"  • {c['name']}")
            lines.append(f"    CPU: {c['cpu_pct']} | Memory: {c['mem_usage']} ({c['mem_pct']})")
            lines.append(f"    State: {c['state']} | Net I/O: {c['net_io']}")
            cpu_val = float(c["cpu_pct"].replace("%", ""))
            if cpu_val < 5:
                lines.append(f"    ⚠️ Very low CPU usage — may be over-provisioned")
            elif cpu_val > 80:
                lines.append(f"    🔴 High CPU usage — consider scaling")
        return "\n".join(lines)

    # Single container info
    return (
        f"Container: {result.get('name', 'unknown')}\n"
        f"  Status: {result.get('status', 'unknown')}\n"
        f"  Ports: {result.get('ports', 'none')}"
    )


def _deploy_rollback(args: dict) -> str:
    service = args["service"]
    current = check_service_by_name(service)
    if current is None:
        return f"Service '{service}' not found in tracked list."

    assessment = assess_rollback(service, current)

    lines = [f"Rollback Assessment for {service}:"]
    lines.append(f"  Recommendation: {assessment['recommendation']}")
    lines.append(f"  Severity: {assessment['severity']}")
    lines.append(f"  Current status: {assessment['current_status']}")

    if assessment["reasons"]:
        lines.append("")
        lines.append("Reasons:")
        for reason in assessment["reasons"]:
            prefix = "🚨" if assessment["severity"] == "critical" else "⚠️"
            lines.append(f"  {prefix} {reason}")

    return "\n".join(lines)


def _deploy_cost(args: dict) -> str:
    result = estimate_deployment_cost()

    if "error" in result:
        return f"Cost estimation error: {result['error']}"

    lines = [f"Estimated Monthly Cost: ${result['total_monthly_estimate']:.2f}"]
    lines.append(f"Containers checked: {result['containers_checked']}")
    lines.append("")

    if result.get("breakdown"):
        for b in result["breakdown"]:
            lines.append(f"  • {b['name']}: ${b['total_monthly']:.2f}/mo")
            lines.append(f"    CPU: ${b['estimated_cpu_cost']:.2f} | Memory: ${b['estimated_mem_cost']:.2f}")
            if b.get("utilization_warning"):
                lines.append(f"    ⚠️ Very low CPU utilization — consider downsizing")

    lines.append("")
    lines.append(result.get("note", ""))
    return "\n".join(lines)


def _aws_status(args: dict) -> str:
    return get_inventory_summary()


def _aws_health(args: dict) -> str:
    return check_instance_health(args["instance"])


def _aws_cost(args: dict) -> str:
    return get_cost_summary()


def _aws_network(args: dict) -> str:
    return check_lightsail_network(args["instance"])


def _aws_alarms(args: dict) -> str:
    return get_active_alarms()


# ── Agent class ───────────────────────────────────────────────────────────────

class DeployMonitorAgent(BaseAgent):
    name = "DeployMonitorAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "deploy_health": _deploy_health,
        "deploy_readiness": _deploy_readiness,
        "deploy_track": _deploy_track,
        "deploy_untrack": _deploy_untrack,
        "deploy_list": _deploy_list,
        "deploy_ssl": _deploy_ssl,
        "deploy_port": _deploy_port,
        "deploy_resources": _deploy_resources,
        "deploy_rollback": _deploy_rollback,
        "deploy_cost": _deploy_cost,
        "aws_status": _aws_status,
        "aws_health": _aws_health,
        "aws_cost": _aws_cost,
        "aws_network": _aws_network,
        "aws_alarms": _aws_alarms,
    }
    temperature = 0.2
    max_tool_rounds = 6

    def __init__(
        self,
        context: SessionContext | None = None,
        profile: UserProfile | None = None,
    ) -> None:
        super().__init__(context=context, profile=profile)
        services = list_services()
        print(f"[DeployMonitorAgent] Ready. {services.split(chr(10))[0] if 'Tracking' in services else 'No services tracked yet.'}", flush=True)

    def _build_system_prompt(self, query_hint: str = "") -> str:
        """Inject live infra config into the system prompt at turn time."""
        base = super()._build_system_prompt(query_hint=query_hint)
        infra_lines = []
        name = self._profile.name if self._profile else "boss"
        if AWS_ACCOUNT_ID:
            infra_lines.append(f"AWS account: {AWS_ACCOUNT_ID}, region: {AWS_DEFAULT_REGION}.")
        if AWS_LIGHTSAIL_INSTANCE:
            ip_part = f" (IP {AWS_LIGHTSAIL_IP})" if AWS_LIGHTSAIL_IP else ""
            infra_lines.append(f"Current Lightsail instance: {AWS_LIGHTSAIL_INSTANCE}{ip_part}.")
        if infra_lines:
            block = f"\n\nAWS INFRA ({name}): " + " ".join(infra_lines)
            return base + block
        return base
