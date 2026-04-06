"""Deployment monitoring voice tool — HTTP health, AWS, SSL, readiness, rollback."""

from __future__ import annotations

from tools.deploy_monitor import (
    check_all_services as _deploy_check_all,
    check_service_by_name as _deploy_check_by_name,
    add_service as _deploy_add_service,
    remove_service as _deploy_remove_service,
    list_services as _deploy_list_services,
    check_ssl_cert as _deploy_check_ssl,
    check_port as _deploy_check_port,
    check_resource_usage as _deploy_check_resources,
    assess_rollback as _deploy_assess_rollback,
    estimate_deployment_cost as _deploy_estimate_cost,
    score_readiness as _deploy_score_readiness,
    aws_status as _deploy_aws_status,
)


def exec_deploy_monitor(action: str, service: str = "", url: str = "",
                        domain: str = "", host: str = "", port: int = 0,
                        env: str = "production", env_vars: str = "", **_kw) -> str:
    """Master deploy monitor action dispatcher."""

    if action == "aws_status":
        region = env_vars or ""
        result = _deploy_aws_status(region=region)
        lines = []
        instances = result.get("instances", [])
        if not instances:
            lines.append("No instances found in this AWS account.")
            if result.get("issues"):
                lines.append(f"Issues: {'; '.join(result['issues'])}")
            return "\n".join(lines)
        running = [i for i in instances if i.get("state", "").lower() == "running"]
        total_cost = result.get("total_monthly_cost", 0)
        lines.append(f"AWS Infrastructure ({len(instances)} instance(s), ${total_cost:.0f}/mo):")
        for inst in instances:
            name = inst.get("name", "?")
            state = inst.get("state", "?")
            provider = inst.get("provider", "AWS")
            cpu = inst.get("cpu", "?")
            ram = inst.get("ram_gb", "?")
            ip = inst.get("ip", "?")
            lines.append(f"  {state.upper()}: {name} ({provider.lower()}) — {cpu}vCPU/{ram}GB | {ip}")
            cpu_avg = inst.get("cpu_24h_avg")
            cpu_max = inst.get("cpu_24h_max")
            if cpu_avg is not None:
                lines.append(f"    CPU 24h avg={cpu_avg}% max={cpu_max}%")
            analysis = inst.get("analysis", [])
            if analysis:
                lines.append("    Analysis:")
                for a in analysis:
                    lines.append(f"      {a}")
        overall = result.get("overall_analysis", [])
        if overall:
            lines.append("")
            lines.append("Account Summary:")
            for a in overall:
                lines.append(f"  {a}")
        if result.get("issues"):
            lines.append("")
            lines.append(f"Issues: {'; '.join(result['issues'])}")
        return "\n".join(lines)

    if action == "aws_health":
        if not service:
            return "Need instance name. Use aws_status to see all instances."
        from tools.aws_monitor import check_instance_health
        return check_instance_health(service)

    if action == "aws_cost":
        from tools.aws_monitor import get_cost_summary
        return get_cost_summary()

    if action == "aws_network":
        if not service:
            return "Need instance name for network stats."
        from tools.aws_monitor import check_lightsail_network
        return check_lightsail_network(service)

    if action == "health":
        if service:
            status = _deploy_check_by_name(service)
            if status is None:
                return f"Service '{service}' not tracked."
            parts = [f"{service}: {status.status}"]
            if status.response_time_ms:
                parts.append(f"{status.response_time_ms}ms")
            if status.error:
                parts.append(status.error)
            return " | ".join(parts)
        results = _deploy_check_all()
        if not results:
            return "No services tracked."
        healthy = sum(1 for r in results if r.healthy)
        down = sum(1 for r in results if r.is_down)
        summary = f"{healthy}/{len(results)} healthy"
        if down:
            summary += f", {down} DOWN"
        details = []
        for r in results:
            icon = "✅" if r.healthy else ("❌" if r.is_down else "⚠️")
            details.append(f"{icon} {r.name}: {r.status}")
        return f"{summary}\n" + "\n".join(details)

    if action == "readiness":
        if not url:
            return "Need a URL to check readiness."
        vars_list = [v.strip() for v in env_vars.split(",") if v.strip()] if env_vars else None
        result = _deploy_score_readiness(url, vars_list)
        lines = [f"Readiness: {result['score']}/100 — {result['verdict']}"]
        for issue in result.get("issues", []):
            lines.append(f"  ⚠️ {issue}")
        return "\n".join(lines) if result["issues"] else lines[0]

    if action == "track":
        if not service or not url:
            return "Need service name and URL to track."
        return _deploy_add_service(service, url, env)

    if action == "untrack":
        if not service:
            return "Need service name to untrack."
        return _deploy_remove_service(service)

    if action == "list":
        return _deploy_list_services()

    if action == "ssl":
        if not domain:
            return "Need a domain to check SSL."
        result = _deploy_check_ssl(domain)
        if not result.get("valid"):
            return f"SSL invalid for {domain}: {result.get('error', '')}"
        warning = " 🚨 EXPIRING SOON" if result.get("critical") else (" ⚠️" if result.get("warning") else "")
        return f"SSL for {domain}: {result['days_left']} days left{warning}"

    if action == "port":
        if not host or not port:
            return "Need host and port to check."
        result = _deploy_check_port(host, port)
        return f"Port {port} on {host}: {'OPEN' if result.get('open') else 'CLOSED'}"

    if action == "resources":
        result = _deploy_check_resources(service or "")
        if "error" in result:
            return f"Resource error: {result['error']}"
        if "containers" in result:
            lines = [f"{result['count']} container(s):"]
            for c in result["containers"]:
                lines.append(f"  {c['name']}: CPU {c['cpu_pct']}, Mem {c['mem_pct']}, {c['state']}")
            return "\n".join(lines)
        return f"Container: {result.get('name', '?')} — {result.get('status', '?')}"

    if action == "rollback":
        if not service:
            return "Need service name to assess rollback."
        current = _deploy_check_by_name(service)
        if current is None:
            return f"Service '{service}' not tracked."
        result = _deploy_assess_rollback(service, current)
        lines = [f"Rollback: {result['recommendation']} ({result['severity']})"]
        for reason in result.get("reasons", []):
            lines.append(f"  • {reason}")
        return "\n".join(lines)

    if action == "cost":
        result = _deploy_estimate_cost()
        if "error" in result:
            return f"Cost error: {result['error']}"
        lines = [f"Est. monthly: ${result['total_monthly_estimate']:.2f}"]
        for b in result.get("breakdown", []):
            if b.get("utilization_warning"):
                lines.append(f"  ⚠️ {b['name']}: ${b['total_monthly']:.2f} (under-utilized)")
        return "\n".join(lines)

    return f"Unknown deploy_monitor action: {action}"
