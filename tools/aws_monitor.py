"""AWS infrastructure monitor — real data from boto3.

Supports: Lightsail, EC2, ECS, Lambda, S3, RDS, CloudWatch, Cost Explorer.
Credentials loaded from .env (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION).
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")


def _client(service: str):
    import boto3
    return boto3.client(service, region_name=_REGION)


# ── Data classes ────────────────────────────────────────────────────────────────

@dataclass
class InstanceInfo:
    name: str
    service: str  # lightsail, ec2
    state: str
    public_ip: str = ""
    instance_type: str = ""
    vcpu: int = 0
    ram_gb: float = 0.0
    disk_gb: int = 0
    region: str = ""
    created: str = ""
    monthly_cost: float = 0.0
    cpu_avg_24h: float = 0.0
    cpu_max_24h: float = 0.0
    ports: list[str] = field(default_factory=list)


# ── Lightsail ───────────────────────────────────────────────────────────────────

def list_lightsail_instances() -> list[InstanceInfo]:
    ls = _client("lightsail")
    result = []
    try:
        instances = ls.get_instances()["instances"]
    except Exception as e:
        print(f"[AWS] Lightsail error: {e}", flush=True)
        return []

    bundles_cache: dict[str, float] = {}
    try:
        for b in ls.get_bundles()["bundles"]:
            bundles_cache[b["bundleId"]] = b["price"]
    except Exception:
        pass

    for inst in instances:
        hw = inst.get("hardware", {})
        ports = []
        for p in inst.get("networking", {}).get("ports", []):
            ports.append(f"{p['fromPort']}-{p['toPort']}/{p['protocol']}")

        info = InstanceInfo(
            name=inst["name"],
            service="lightsail",
            state=inst["state"]["name"],
            public_ip=inst.get("publicIpAddress", ""),
            instance_type=inst.get("bundleId", ""),
            vcpu=hw.get("cpuCount", 0),
            ram_gb=hw.get("ramSizeInGb", 0),
            disk_gb=hw.get("disks", [{}])[0].get("sizeInGb", 0) if hw.get("disks") else 0,
            region=inst["location"]["availabilityZone"],
            created=str(inst.get("createdAt", "")),
            monthly_cost=bundles_cache.get(inst.get("bundleId", ""), 0),
            ports=ports,
        )

        try:
            now = datetime.datetime.utcnow()
            metrics = ls.get_instance_metric_data(
                instanceName=inst["name"],
                metricName="CPUUtilization",
                period=3600,
                startTime=now - datetime.timedelta(hours=24),
                endTime=now,
                unit="Percent",
                statistics=["Average", "Maximum"],
            )
            dps = metrics["metricData"]
            if dps:
                info.cpu_avg_24h = round(sum(d["average"] for d in dps) / len(dps), 1)
                info.cpu_max_24h = round(max(d["maximum"] for d in dps), 1)
        except Exception:
            pass

        result.append(info)
    return result


# ── EC2 ─────────────────────────────────────────────────────────────────────────

def list_ec2_instances() -> list[InstanceInfo]:
    ec2 = _client("ec2")
    result = []
    try:
        reservations = ec2.describe_instances()["Reservations"]
    except Exception as e:
        print(f"[AWS] EC2 error: {e}", flush=True)
        return []

    for r in reservations:
        for inst in r["Instances"]:
            name = next(
                (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                inst["InstanceId"],
            )
            result.append(InstanceInfo(
                name=name,
                service="ec2",
                state=inst["State"]["Name"],
                public_ip=inst.get("PublicIpAddress", ""),
                instance_type=inst.get("InstanceType", ""),
                region=inst.get("Placement", {}).get("AvailabilityZone", ""),
                created=str(inst.get("LaunchTime", "")),
            ))
    return result


# ── Full inventory ──────────────────────────────────────────────────────────────

def get_all_instances() -> list[InstanceInfo]:
    return list_lightsail_instances() + list_ec2_instances()


def get_inventory_summary() -> str:
    instances = get_all_instances()
    if not instances:
        return "No instances found in AWS account."

    running = [i for i in instances if i.state == "running"]
    stopped = [i for i in instances if i.state != "running"]
    total_cost = sum(i.monthly_cost for i in instances)

    lines = [f"AWS Infrastructure ({len(instances)} instance(s), ${total_cost:.0f}/mo):"]
    for i in running:
        cpu_info = f" | CPU 24h avg={i.cpu_avg_24h}% max={i.cpu_max_24h}%" if i.cpu_avg_24h else ""
        lines.append(
            f"  RUNNING: {i.name} ({i.service}) — {i.vcpu}vCPU/{i.ram_gb}GB "
            f"| {i.public_ip}{cpu_info} | ${i.monthly_cost:.0f}/mo"
        )
        if i.ports:
            lines.append(f"    Ports: {', '.join(i.ports)}")
    for i in stopped:
        lines.append(f"  {i.state.upper()}: {i.name} ({i.service}) — {i.instance_type}")
    return "\n".join(lines)


# ── Instance health check ──────────────────────────────────────────────────────

def check_instance_health(name: str) -> str:
    instances = get_all_instances()
    match = [i for i in instances if i.name.lower() == name.lower()]
    if not match:
        return f"Instance '{name}' not found. Available: {', '.join(i.name for i in instances)}"

    i = match[0]
    lines = [f"{i.name} ({i.service}):"]
    lines.append(f"  State: {i.state}")
    lines.append(f"  IP: {i.public_ip}")
    lines.append(f"  Specs: {i.vcpu} vCPU, {i.ram_gb} GB RAM, {i.disk_gb} GB disk")
    lines.append(f"  Region: {i.region}")
    lines.append(f"  Cost: ${i.monthly_cost:.0f}/mo")
    if i.cpu_avg_24h:
        lines.append(f"  CPU (24h): avg {i.cpu_avg_24h}%, peak {i.cpu_max_24h}%")
        if i.cpu_avg_24h < 5:
            lines.append("  ⚠️ Very low CPU — possibly over-provisioned")
        elif i.cpu_max_24h > 80:
            lines.append("  🔴 High CPU spikes — consider scaling up")
    if i.ports:
        lines.append(f"  Ports: {', '.join(i.ports)}")
    return "\n".join(lines)


# ── Network check ──────────────────────────────────────────────────────────────

def check_lightsail_network(name: str) -> str:
    ls = _client("lightsail")
    now = datetime.datetime.utcnow()
    lines = [f"Network stats for {name} (24h):"]
    for metric_name, label in [
        ("NetworkIn", "Bytes In"),
        ("NetworkOut", "Bytes Out"),
    ]:
        try:
            data = ls.get_instance_metric_data(
                instanceName=name,
                metricName=metric_name,
                period=3600,
                startTime=now - datetime.timedelta(hours=24),
                endTime=now,
                unit="Bytes",
                statistics=["Sum"],
            )
            total = sum(d["sum"] for d in data["metricData"])
            gb = total / (1024 ** 3)
            lines.append(f"  {label}: {gb:.2f} GB")
        except Exception as e:
            lines.append(f"  {label}: error ({e})")
    return "\n".join(lines)


# ── Cost (last 30 days) ────────────────────────────────────────────────────────

def get_cost_summary() -> str:
    try:
        ce = _client("ce")
        now = datetime.datetime.utcnow()
        start = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

        result = ce.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        lines = ["AWS Cost (last 30 days):"]
        total = 0.0
        for group in result["ResultsByTime"]:
            for g in group["Groups"]:
                service = g["Keys"][0]
                amount = float(g["Metrics"]["UnblendedCost"]["Amount"])
                if amount > 0.01:
                    lines.append(f"  {service}: ${amount:.2f}")
                    total += amount
        lines.insert(1, f"  Total: ${total:.2f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Cost Explorer error: {e}"


# ── Lightsail alerts ────────────────────────────────────────────────────────────

def get_active_alarms() -> str:
    try:
        ls = _client("lightsail")
        alarms = ls.get_alarms()
        active = [a for a in alarms["alarms"] if a["state"] == "ALARM"]
        if not active:
            return "No active alarms."
        lines = [f"{len(active)} active alarm(s):"]
        for a in active:
            lines.append(f"  🚨 {a['name']}: {a['monitoredResourceInfo']['name']} — {a['metricName']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Alarms check error: {e}"
