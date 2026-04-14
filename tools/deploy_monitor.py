"""
Deployment Monitoring Utilities — health checks, SSL, readiness scoring.

Used by DeployMonitorAgent and the awareness loop.
No LLM dependency — pure infrastructure checks.
"""

from __future__ import annotations

import json
import os
import ssl
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

# ── Tracked services persistence ─────────────────────────────────────────────

SERVICES_PATH = os.path.expanduser("~/.clawspan_deploy_services.json")


@dataclass
class ServiceStatus:
    """Result of a single service health check."""
    name: str
    url: str = ""
    status: str = "unknown"  # healthy, degraded, down, unknown
    status_code: int = 0
    response_time_ms: float = 0.0
    ssl_days_left: int = 0
    ssl_valid: bool = False
    error: str = ""
    last_check: str = ""
    uptime_checks: int = 0
    down_checks: int = 0

    @property
    def healthy(self) -> bool:
        return self.status == "healthy"

    @property
    def degraded(self) -> bool:
        return self.status == "degraded"

    @property
    def is_down(self) -> bool:
        return self.status == "down"


@dataclass
class TrackedService:
    """A service being monitored."""
    name: str
    url: str
    env: str = "production"  # production, staging, canary
    expected_status: int = 200
    timeout: float = 10.0
    check_interval: int = 300  # seconds
    last_status: str = "unknown"
    added_at: str = ""

    def __post_init__(self):
        if not self.added_at:
            self.added_at = datetime.now().isoformat()


def _load_services() -> list[dict]:
    if os.path.exists(SERVICES_PATH):
        try:
            with open(SERVICES_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_services(services: list[dict]) -> None:
    try:
        with open(SERVICES_PATH, "w") as f:
            json.dump(services, f, indent=2)
    except Exception as e:
        print(f"[DeployMonitor] Save error: {e}", flush=True)


# ── Core Health Checks ───────────────────────────────────────────────────────

def check_health(url: str, timeout: float = 10.0,
                 expected_status: int = 200) -> ServiceStatus:
    """HTTP health check — GET the URL, measure response time, check status."""
    name = url.split("://")[-1].split("/")[0] if "://" in url else url.split("/")[0]
    result = ServiceStatus(name=name, url=url, last_check=datetime.now().isoformat())

    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Clawspan-DeployMonitor/1.0")

        # Skip SSL verification for self-signed certs in staging
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            elapsed = (time.monotonic() - start) * 1000
            result.status_code = resp.status
            result.response_time_ms = round(elapsed, 1)

            if resp.status == expected_status:
                if elapsed < 500:
                    result.status = "healthy"
                elif elapsed < 2000:
                    result.status = "degraded"
                else:
                    result.status = "degraded"
                    result.error = f"Slow response: {elapsed:.0f}ms"
            elif resp.status >= 500:
                result.status = "down"
                result.error = f"Server error: {resp.status}"
            elif resp.status >= 400:
                result.status = "degraded"
                result.error = f"Client error: {resp.status}"
            else:
                result.status = "degraded"
                result.error = f"Unexpected status: {resp.status}"

    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - start) * 1000
        result.status_code = e.code
        result.response_time_ms = round(elapsed, 1)
        result.status = "down" if e.code >= 500 else "degraded"
        result.error = f"HTTP {e.code}: {e.reason}"

    except urllib.error.URLError as e:
        result.status = "down"
        result.error = f"Connection failed: {e.reason}"

    except socket.timeout:
        result.status = "down"
        result.error = "Connection timed out"

    except Exception as e:
        result.status = "unknown"
        result.error = str(e)

    # Check SSL cert
    if url.startswith("https://"):
        ssl_info = check_ssl_cert(name)
        result.ssl_days_left = ssl_info.get("days_left", 0)
        result.ssl_valid = ssl_info.get("valid", False)

    return result


def check_port(host: str, port: int, timeout: float = 5.0) -> dict:
    """TCP port reachability check."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.monotonic()
        result = sock.connect_ex((host, port))
        elapsed = (time.monotonic() - start) * 1000
        sock.close()

        if result == 0:
            return {
                "host": host,
                "port": port,
                "open": True,
                "response_time_ms": round(elapsed, 1),
            }
        return {
            "host": host,
            "port": port,
            "open": False,
            "error": f"Port {port} is not reachable on {host}",
        }
    except socket.timeout:
        return {
            "host": host,
            "port": port,
            "open": False,
            "error": f"Connection to {host}:{port} timed out",
        }
    except Exception as e:
        return {
            "host": host,
            "port": port,
            "open": False,
            "error": str(e),
        }


def check_ssl_cert(domain: str, port: int = 443) -> dict:
    """Check SSL certificate validity and days until expiry."""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return {"valid": False, "error": "No certificate found"}

                # Parse expiry
                not_after = cert.get("notAfter", "")
                if not_after:
                    # Format: 'Apr 13 12:00:00 2026 GMT'
                    expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                    days_left = (expiry - datetime.now()).days
                    issuer = cert.get("issuer", ())
                    issuer_str = ""
                    for rdn in issuer:
                        for k, v in rdn:
                            if "organization" in k.lower() or "common" in k.lower():
                                issuer_str = v
                    return {
                        "valid": True,
                        "days_left": days_left,
                        "expires": not_after,
                        "issuer": issuer_str,
                        "warning": days_left <= 30,
                        "critical": days_left <= 7,
                    }

                return {"valid": True, "days_left": 0}

    except ssl.CertificateError as e:
        return {"valid": False, "error": f"Certificate error: {e}"}
    except socket.timeout:
        return {"valid": False, "error": "Connection timed out"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def check_env_vars(required_vars: list[str], env_file: str = "") -> dict:
    """Check if required environment variables are set.

    Can check current process env or a .env file.
    """
    results = {"total": len(required_vars), "missing": [], "present": []}

    if env_file and os.path.exists(env_file):
        # Parse .env file
        env_vars = {}
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip().strip('"').strip("'")

        for var in required_vars:
            if var in env_vars and env_vars[var]:
                results["present"].append(var)
            else:
                results["missing"].append(var)

    else:
        # Check current process environment
        for var in required_vars:
            if os.environ.get(var):
                results["present"].append(var)
            else:
                results["missing"].append(var)

    results["all_set"] = len(results["missing"]) == 0
    return results


def check_resource_usage(service_name: str) -> dict:
    """Check Docker container resource usage.

    Returns CPU%, memory usage, status, and uptime.
    """
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.State}}"],
            capture_output=True, text=True, timeout=15,
        )

        if result.returncode != 0:
            return {"error": f"Docker command failed: {result.stderr.strip()}"}

        containers = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 6:
                containers.append({
                    "name": parts[0],
                    "cpu_pct": parts[1],
                    "mem_usage": parts[2],
                    "mem_pct": parts[3],
                    "net_io": parts[4],
                    "state": parts[5],
                })

        # Filter by service name
        if service_name:
            containers = [c for c in containers if service_name.lower() in c["name"].lower()]

        if not containers:
            # Try docker ps as fallback
            ps_result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
                capture_output=True, text=True, timeout=10,
            )
            if ps_result.returncode == 0:
                for line in ps_result.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 2 and service_name.lower() in parts[0].lower():
                        return {
                            "name": parts[0],
                            "status": parts[1],
                            "ports": parts[2] if len(parts) > 2 else "",
                            "note": "Resource stats unavailable (docker stats not running)",
                        }
            return {"error": f"No container found matching '{service_name}'"}

        return {"containers": containers, "count": len(containers)}

    except FileNotFoundError:
        return {"error": "Docker is not installed or not in PATH"}
    except subprocess.TimeoutExpired:
        return {"error": "Docker command timed out"}
    except Exception as e:
        return {"error": str(e)}


# ── Production Readiness Scoring ─────────────────────────────────────────────

def score_readiness(url: str, required_env_vars: list[str] | None = None,
                    expected_containers: int = 1) -> dict:
    """Score a deployment's production readiness.

    Checks:
    1. Health endpoint (25 points)
    2. SSL certificate validity (15 points)
    3. Response time < 500ms (15 points)
    4. Required env vars set (15 points)
    5. Container health & count (15 points)
    6. No error responses (15 points)

    Returns: score (0-100), verdict (READY/RISKY/NOT_READY), issues list.
    """
    score = 0
    max_score = 100
    issues = []
    checks = {}

    # 1. Health check (25 pts)
    health = check_health(url)
    if health.healthy:
        score += 25
        checks["health"] = "OK"
    elif health.degraded:
        score += 10
        checks["health"] = f"DEGRADED ({health.error})"
        issues.append(f"Health check degraded: {health.error}")
    else:
        checks["health"] = f"DOWN ({health.error})"
        issues.append(f"Service is down: {health.error}")

    # 2. SSL certificate (15 pts)
    if url.startswith("https://"):
        ssl_info = check_ssl_cert(health.name)
        if ssl_info.get("valid"):
            if ssl_info.get("critical"):
                score += 0
                checks["ssl"] = f"CRITICAL — {ssl_info['days_left']} days left"
                issues.append(f"SSL certificate expires in {ssl_info['days_left']} days!")
            elif ssl_info.get("warning"):
                score += 8
                checks["ssl"] = f"WARNING — {ssl_info['days_left']} days left"
                issues.append(f"SSL certificate expires in {ssl_info['days_left']} days")
            else:
                score += 15
                checks["ssl"] = f"OK ({ssl_info['days_left']} days left)"
        else:
            checks["ssl"] = f"INVALID — {ssl_info.get('error', 'unknown')}"
            issues.append(f"SSL certificate invalid: {ssl_info.get('error', '')}")
    else:
        score += 5  # partial credit for HTTP (non-ideal but not broken)
        checks["ssl"] = "HTTP only — no SSL"
        issues.append("Service not using HTTPS")

    # 3. Response time (15 pts)
    if health.response_time_ms > 0:
        if health.response_time_ms < 200:
            score += 15
            checks["response_time"] = f"Excellent ({health.response_time_ms}ms)"
        elif health.response_time_ms < 500:
            score += 12
            checks["response_time"] = f"Good ({health.response_time_ms}ms)"
        elif health.response_time_ms < 1000:
            score += 8
            checks["response_time"] = f"Acceptable ({health.response_time_ms}ms)"
        elif health.response_time_ms < 2000:
            score += 4
            checks["response_time"] = f"Slow ({health.response_time_ms}ms)"
            issues.append(f"Response time slow: {health.response_time_ms}ms")
        else:
            score += 0
            checks["response_time"] = f"Very slow ({health.response_time_ms}ms)"
            issues.append(f"Response time very slow: {health.response_time_ms}ms")
    else:
        checks["response_time"] = "N/A — service unreachable"

    # 4. Environment variables (15 pts)
    if required_env_vars:
        env_check = check_env_vars(required_env_vars)
        missing_count = len(env_check["missing"])
        if missing_count == 0:
            score += 15
            checks["env_vars"] = "All set"
        elif missing_count <= 2:
            score += 8
            checks["env_vars"] = f"{missing_count} missing: {', '.join(env_check['missing'][:3])}"
            issues.append(f"Missing env vars: {', '.join(env_check['missing'][:3])}")
        else:
            score += 0
            checks["env_vars"] = f"{missing_count} missing"
            issues.append(f"Missing {missing_count} env vars: {', '.join(env_check['missing'][:5])}")
    else:
        score += 10  # partial — can't fully check without requirements
        checks["env_vars"] = "Not checked (no requirements provided)"

    # 5. Container health (15 pts)
    resources = check_resource_usage("")
    if "error" not in resources and "containers" in resources:
        container_count = resources["count"]
        if container_count >= expected_containers:
            score += 15
            checks["containers"] = f"OK ({container_count} running)"
        elif container_count > 0:
            score += 8
            checks["containers"] = f"Partial ({container_count}/{expected_containers} running)"
            issues.append(f"Only {container_count}/{expected_containers} containers running")
        else:
            score += 0
            checks["containers"] = "No containers found"
            issues.append("No containers running")
    elif "error" not in resources and "name" in resources:
        score += 10  # container found but no stats
        checks["containers"] = f"Found ({resources['status']})"
    else:
        score += 5  # partial — docker may not be available
        checks["containers"] = "Docker check skipped"

    # 6. No error responses (15 pts)
    if not health.error:
        score += 15
        checks["errors"] = "No errors"
    elif "slow" in health.error.lower() or "unexpected" in health.error.lower():
        score += 8
        checks["errors"] = f"Minor: {health.error}"
    else:
        score += 0
        checks["errors"] = f"Error: {health.error}"

    # Verdict
    if score >= 80:
        verdict = "READY"
    elif score >= 50:
        verdict = "RISKY"
    else:
        verdict = "NOT_READY"

    return {
        "url": url,
        "score": score,
        "max_score": max_score,
        "verdict": verdict,
        "checks": checks,
        "issues": issues,
        "status_code": health.status_code,
        "response_time_ms": health.response_time_ms,
        "checked_at": datetime.now().isoformat(),
    }


# ── Service Tracking ─────────────────────────────────────────────────────────

def add_service(name: str, url: str, env: str = "production",
                timeout: float = 10.0) -> str:
    """Add a service to the tracked list."""
    services = _load_services()

    # Check for duplicate
    for s in services:
        if s["name"].lower() == name.lower() or s["url"] == url:
            return f"Service '{s['name']}' already tracked at {s['url']}"

    services.append({
        "name": name,
        "url": url,
        "env": env,
        "timeout": timeout,
        "added_at": datetime.now().isoformat(),
    })
    _save_services(services)
    return f"Now tracking {name} at {url} ({env})"


def remove_service(name: str) -> str:
    """Stop tracking a service."""
    services = _load_services()
    original_len = len(services)
    services = [s for s in services if s["name"].lower() != name.lower()]

    if len(services) == original_len:
        return f"Service '{name}' not found in tracked list"

    _save_services(services)
    return f"Stopped tracking {name}"


def list_services() -> str:
    """List all tracked services with their latest status."""
    services = _load_services()
    if not services:
        return "No services tracked. Say 'track myservice at https://example.com' to start."

    lines = [f"Tracking {len(services)} service(s):"]
    for s in services:
        env_tag = f"[{s.get('env', 'production').upper()}]"
        lines.append(f"  • {s['name']} {env_tag} → {s['url']}")
    return "\n".join(lines)


def check_all_services() -> list[ServiceStatus]:
    """Run health checks on all tracked services."""
    services = _load_services()
    results = []

    for s in services:
        status = check_health(
            s["url"],
            timeout=s.get("timeout", 10.0),
            expected_status=s.get("expected_status", 200),
        )
        status.name = s["name"]
        results.append(status)

    return results


def check_service_by_name(name: str) -> ServiceStatus | None:
    """Find and check a tracked service by name."""
    services = _load_services()
    for s in services:
        if s["name"].lower() == name.lower():
            return check_health(
                s["url"],
                timeout=s.get("timeout", 10.0),
                expected_status=s.get("expected_status", 200),
            )
    return None


# ── Rollback Assessment ──────────────────────────────────────────────────────

def assess_rollback(service_name: str, current_status: ServiceStatus,
                    previous_status: ServiceStatus | None = None) -> dict:
    """Assess whether a service should be rolled back based on health comparison.

    Returns: recommendation (ROLLBACK/MONITOR/OK), reasoning, severity.
    """
    reasons = []
    severity = "low"

    if current_status.is_down:
        reasons.append(f"Service is DOWN: {current_status.error}")
        severity = "critical"
    elif current_status.degraded:
        reasons.append(f"Service degraded: {current_status.error}")
        severity = "high"

    # Compare with previous status
    if previous_status:
        if previous_status.healthy and current_status.is_down:
            reasons.append("Was healthy, now down — strong rollback signal")
            severity = "critical"
        elif previous_status.response_time_ms > 0 and current_status.response_time_ms > 0:
            slowdown = current_status.response_time_ms / max(previous_status.response_time_ms, 1)
            if slowdown > 3:
                reasons.append(f"Response time {slowdown:.1f}x slower than before")
                if severity not in ("critical",):
                    severity = "high"

    # SSL check
    if current_status.ssl_valid and current_status.ssl_days_left <= 7:
        reasons.append(f"SSL certificate expires in {current_status.ssl_days_left} days")
        if severity == "low":
            severity = "high"

    # Recommendation
    if severity == "critical":
        recommendation = "ROLLBACK"
    elif severity in ("high",) and len(reasons) >= 2:
        recommendation = "ROLLBACK"
    elif severity == "high":
        recommendation = "MONITOR"
    else:
        recommendation = "OK"

    return {
        "service": service_name,
        "recommendation": recommendation,
        "severity": severity,
        "reasons": reasons,
        "current_status": current_status.status,
        "current_response_time_ms": current_status.response_time_ms,
    }


# ── Cost Estimation ──────────────────────────────────────────────────────────

def estimate_deployment_cost(containers: list[dict] | None = None) -> dict:
    """Estimate monthly deployment cost based on resource allocation.

    Uses rough cloud pricing: $0.0476/vCPU-hour, $0.00495/GB-hour (GCP-like).
    """
    if containers is None:
        resources = check_resource_usage("")
        if "containers" not in resources:
            return {"error": resources.get("error", "Cannot assess resources")}
        containers = resources["containers"]

    total_monthly = 0.0
    breakdown = []

    for c in containers:
        # Parse CPU% and memory
        cpu_str = c.get("cpu_pct", "0%").replace("%", "")
        mem_str = c.get("mem_usage", "0B / 0B")

        try:
            cpu_pct = float(cpu_str)
        except ValueError:
            cpu_pct = 0

        # Parse memory (e.g. "256.5MiB / 1.952GiB")
        mem_used = "0"
        mem_limit = "0"
        parts = mem_str.split("/")
        if len(parts) == 2:
            mem_used = parts[0].strip()
            mem_limit = parts[1].strip()

        # Estimate: assume 2 vCPU per container at ~30% avg usage
        vcpu = 2
        mem_gb = 2  # default assumption

        # Monthly cost per container
        cpu_cost = vcpu * 0.0476 * 730  # hours per month
        mem_cost = mem_gb * 0.00495 * 730
        container_cost = cpu_cost * (cpu_pct / 100) + mem_cost
        total_monthly += container_cost

        breakdown.append({
            "name": c.get("name", "unknown"),
            "estimated_cpu_cost": round(cpu_cost * (cpu_pct / 100), 2),
            "estimated_mem_cost": round(mem_cost, 2),
            "total_monthly": round(container_cost, 2),
            "utilization_warning": cpu_pct < 15,  # under-utilized
        })

    return {
        "containers_checked": len(breakdown),
        "total_monthly_estimate": round(total_monthly, 2),
        "breakdown": breakdown,
        "note": "Estimate based on current resource usage. Actual costs depend on provider and plan.",
    }


# ── AWS Infrastructure Status ────────────────────────────────────────────────

def aws_status(region: str = "") -> dict:
    """Query AWS Lightsail + EC2 for running instances, with health analysis.

    Primary: boto3 (aws_monitor module) for real CloudWatch metrics.
    Fallback: aws CLI if boto3 isn't available.
    Returns instance list, costs, and a situational analysis explaining
    WHAT each metric means and WHY it matters.
    """
    results: dict[str, Any] = {
        "instances": [],
        "total_monthly_cost": 0.0,
        "issues": [],
        "analysis": [],
        "overall_analysis": [],
    }

    # ── Primary: boto3 via aws_monitor ──────────────────────────────────
    try:
        from tools.aws_monitor import list_lightsail_instances, list_ec2_instances

        all_instances = list_lightsail_instances() + list_ec2_instances()
        if not all_instances:
            results["overall_analysis"] = ["No instances found. Account may be empty or credentials not configured."]
            return results

        for inst in all_instances:
            instance_data = {
                "name": inst.name,
                "type": inst.service,
                "state": inst.state,
                "ip": inst.public_ip or "no public IP",
                "cpu": inst.vcpu,
                "ram_gb": inst.ram_gb,
                "monthly_cost": inst.monthly_cost,
                "provider": f"AWS {inst.service.title()}",
                "blueprint": inst.instance_type if inst.service == "lightsail" else "",
                "instance_type": inst.instance_type,
                "ports": inst.ports if hasattr(inst, "ports") else [],
                "cpu_24h_avg": inst.cpu_avg_24h if hasattr(inst, "cpu_avg_24h") else None,
                "cpu_24h_max": inst.cpu_max_24h if hasattr(inst, "cpu_max_24h") else None,
                "region": inst.region,
                "created": inst.created,
                "disk_gb": inst.disk_gb if hasattr(inst, "disk_gb") else 0,
            }

            # Generate situational analysis
            instance_data["analysis"] = _analyze_instance(instance_data)
            results["instances"].append(instance_data)
            results["total_monthly_cost"] += inst.monthly_cost

        results["overall_analysis"] = _analyze_account(results)
        return results

    except ImportError:
        results["issues"].append("boto3 not available — falling back to AWS CLI")
    except Exception as e:
        results["issues"].append(f"boto3 error: {e} — falling back to AWS CLI")

    # ── Fallback: AWS CLI ───────────────────────────────────────────────
    try:
        ls_args = ["aws", "lightsail", "get-instances", "--output", "json"]
        if region:
            ls_args += ["--region", region]
        ls_result = subprocess.run(ls_args, shell=False, capture_output=True, text=True, timeout=30)
        if ls_result.returncode == 0:
            data = json.loads(ls_result.stdout) if ls_result.stdout.strip() else {}
            for inst in data.get("instances", []):
                hw = inst.get("hardware", {})
                instance_data = {
                    "name": inst["name"],
                    "type": "lightsail",
                    "state": inst.get("state", {}).get("name", "unknown"),
                    "ip": inst.get("publicIpAddress", "no public IP"),
                    "cpu": hw.get("cpuCount", 0),
                    "ram_gb": hw.get("ramSizeInGb", 0),
                    "monthly_cost": 0,
                    "provider": "AWS Lightsail",
                    "blueprint": inst.get("blueprintId", ""),
                }
                instance_data["analysis"] = _analyze_instance(instance_data)
                results["instances"].append(instance_data)

        results["overall_analysis"] = _analyze_account(results)
    except Exception as e:
        results["issues"].append(f"AWS CLI error: {e}")
        if not results["overall_analysis"]:
            results["overall_analysis"] = [f"AWS query failed: {e}"]

    return results


def _get_lightsail_cpu_metrics(instance_name: str, region: str) -> dict:
    """Fetch 24h CPU utilization from CloudWatch for a Lightsail instance."""
    try:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)
        # ISO 8601 strings that AWS CLI accepts
        start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        avg_args = [
            "aws", "lightsail", "get-instance-metric-data",
            "--instance-name", instance_name,
            "--metric-name", "CPUUtilization",
            "--unit", "Percent",
            "--period", "3600",
            "--start-time", start_str,
            "--end-time", end_str,
            "--statistics", "Average",
            "--output", "json",
        ]
        if region:
            avg_args += ["--region", region]

        avg_result = subprocess.run(avg_args, shell=False, capture_output=True, text=True, timeout=20)
        if avg_result.returncode == 0:
            data = json.loads(avg_result.stdout)
            points = data.get("metricData", [])
            if points:
                values = [p.get("average", 0) for p in points if p.get("average") is not None]
                if values:
                    avg_24h = round(sum(values) / len(values), 1)
                    max_24h = round(max(values), 1)
                    return {
                        "cpu_24h_avg": avg_24h,
                        "cpu_24h_max": max_24h,
                        "cpu_samples": len(values),
                    }
    except Exception:
        pass
    return {}


def _ec2_type_to_resources(instance_type: str) -> tuple[int, float]:
    """Map EC2 instance type to vCPU count and RAM in GB."""
    type_map = {
        "t2.micro": (1, 1.0), "t2.small": (1, 2.0), "t2.medium": (2, 4.0),
        "t2.large": (2, 8.0), "t2.xlarge": (4, 16.0),
        "t3.micro": (2, 1.0), "t3.small": (2, 2.0), "t3.medium": (2, 4.0),
        "t3.large": (2, 8.0), "t3.xlarge": (4, 16.0),
        "t3a.micro": (2, 1.0), "t3a.small": (2, 2.0), "t3a.medium": (2, 4.0),
        "m5.large": (2, 8.0), "m5.xlarge": (4, 16.0),
        "c5.large": (2, 4.0), "c5.xlarge": (4, 8.0),
    }
    return type_map.get(instance_type, (2, 4.0))  # default guess


def _ec2_estimate_monthly(instance_type: str) -> float:
    """Rough monthly cost for an EC2 instance type (on-demand, us-east-1)."""
    cost_map = {
        "t2.micro": 8.5, "t2.small": 17, "t2.medium": 34, "t2.large": 68,
        "t3.micro": 7.6, "t3.small": 15, "t3.medium": 30, "t3.large": 60,
        "t3a.micro": 6.8, "t3a.small": 14, "t3a.medium": 28,
        "m5.large": 70, "m5.xlarge": 140,
        "c5.large": 62, "c5.xlarge": 124,
    }
    return cost_map.get(instance_type, 30.0)  # default guess


def _analyze_instance(data: dict) -> list[str]:
    """Generate situational analysis for a single instance.

    Explains WHAT each metric means and WHY it matters — not just raw numbers.
    """
    analysis = []
    state = data.get("state", "").lower()
    name = data.get("name", "unknown")
    provider = data.get("provider", "AWS")

    # ── State analysis ──────────────────────────────────────────────────
    if state == "running":
        analysis.append(f"✅ {name} is RUNNING — it's actively consuming resources and billed hourly.")
    elif state == "stopped":
        analysis.append(f"⏸️ {name} is STOPPED — you're not billed for compute, but storage (EBS/Snapshots) still costs money.")
    elif state == "pending":
        analysis.append(f"🔄 {name} is PENDING — it's booting up. If this persists >5 min, there may be a launch issue.")
    else:
        analysis.append(f"⚠️ {name} state: {state} — check AWS console for details.")

    # ── CPU analysis ────────────────────────────────────────────────────
    cpu_avg = data.get("cpu_24h_avg")
    cpu_max = data.get("cpu_24h_max")

    if cpu_avg is not None:
        if cpu_avg < 5:
            analysis.append(
                f"📉 CPU averaging {cpu_avg}% over 24h — this instance is essentially idle. "
                f"This means either (a) it's a standby/backup server, or (b) "
                f"the workload isn't routing traffic here. If it should be serving traffic, "
                f"check your load balancer or DNS configuration."
            )
        elif cpu_avg < 30:
            analysis.append(
                f"📊 CPU averaging {cpu_avg}% — light load. The instance has plenty of headroom. "
                f"If this is a development or staging server, that's normal. "
                f"For production, consider downsizing to save costs."
            )
        elif cpu_avg < 70:
            analysis.append(
                f"📈 CPU at {cpu_avg}% — healthy utilization. "
                f"This indicates active workloads with room for traffic spikes. "
                f"Peak hit {cpu_max}% — within safe limits."
            )
        elif cpu_avg < 90:
            analysis.append(
                f"🔥 CPU at {cpu_avg}% — high utilization. "
                f"Your instance is working hard. If traffic grows, you'll hit throttling. "
                f"Consider scaling horizontally (add instances) or vertically (upgrade type)."
            )
        else:
            analysis.append(
                f"🚨 CPU at {cpu_avg}% — critically high! "
                f"This instance is CPU-bound. Expect slow response times, timeouts, and poor user experience. "
                f"Peak was {cpu_max}%. Immediate action needed: scale up or optimize workloads."
            )

    # ── Resource sizing ─────────────────────────────────────────────────
    cpu_count = data.get("cpu", 0)
    ram_gb = data.get("ram_gb", 0)
    cost = data.get("monthly_cost", 0)

    if cpu_count and cpu_avg is not None and cpu_avg < 10 and cost > 20:
        analysis.append(
            f"💰 Cost optimization: paying ${cost:.0f}/mo for {cpu_count} vCPU/{ram_gb}GB RAM "
            f"at {cpu_avg}% utilization. You could downgrade to a smaller instance "
            f"and save ~50-70%."
        )

    # ── Uptime / launch analysis ────────────────────────────────────────
    launch = data.get("launch_time", "")
    if launch:
        try:
            launch_date = datetime.strptime(launch, "%Y-%m-%d")
            days_up = (datetime.now() - launch_date).days
            if days_up > 180:
                analysis.append(
                    f"📅 Instance running for {days_up} days without restart. "
                    f"Long uptime is generally good, but consider periodic reboots "
                    f"to apply kernel updates and clear memory leaks."
                )
        except Exception:
            pass

    # ── Blueprint / OS analysis ─────────────────────────────────────────
    blueprint = data.get("blueprint", "")
    if blueprint and blueprint != "unknown":
        analysis.append(f"🖥️ Running {blueprint} — verify this OS matches your deployment requirements.")

    return analysis


def _analyze_account(results: dict) -> list[str]:
    """Generate overall AWS account analysis."""
    analysis = []
    instances = results["instances"]
    total_cost = results["total_monthly_cost"]
    issues = results["issues"]

    if not instances:
        analysis.append("No running instances found in this account. Either all are stopped or this is a fresh account.")
        return analysis

    running = [i for i in instances if i.get("state", "").lower() == "running"]
    idle = [i for i in running if i.get("cpu_24h_avg", 100) < 10]
    overloaded = [i for i in running if i.get("cpu_24h_avg", 0) > 80]

    # Summary
    analysis.append(
        f"You have {len(instances)} instance(s) tracked: "
        f"{len(running)} running, {len(instances) - len(running)} not running. "
        f"Estimated monthly cost: ${total_cost:.2f}."
    )

    if idle:
        idle_names = ", ".join(i["name"] for i in idle)
        analysis.append(
            f"⚠️ {len(idle)} instance(s) are essentially idle (<10% CPU): {idle_names}. "
            f"If these aren't serving traffic, you're paying for nothing. "
            f"Consider stopping them or downsizing."
        )

    if overloaded:
        overload_names = ", ".join(i["name"] for i in overloaded)
        analysis.append(
            f"🚨 {len(overloaded)} instance(s) are overloaded (>80% CPU): {overload_names}. "
            f"These are performance bottlenecks and will degrade user experience."
        )

    if issues:
        analysis.append(f"Issues encountered: {'; '.join(issues)}")

    return analysis
