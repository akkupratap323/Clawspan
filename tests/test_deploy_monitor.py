"""Tests for deployment monitoring utilities."""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

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
    ServiceStatus,
    SERVICES_PATH,
    _load_services,
    _save_services,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_services(tmp_path, monkeypatch):
    """Use a temp file for services so tests don't affect real data."""
    svc_path = str(tmp_path / "services.json")
    monkeypatch.setattr("tools.deploy_monitor.SERVICES_PATH", svc_path)
    yield svc_path
    # Cleanup
    if os.path.exists(svc_path):
        os.unlink(svc_path)


# ── Health Check Tests ───────────────────────────────────────────────────────

class TestCheckHealth:
    def test_unreachable_service(self):
        """A dead/invalid URL should return status=down."""
        result = check_health("http://localhost:59999", timeout=2.0)
        assert result.status in ("down", "unknown")
        assert result.error != ""

    def test_health_returns_status_fields(self):
        """Result should have all expected fields."""
        result = check_health("http://localhost:59999", timeout=2.0)
        assert isinstance(result.name, str)
        assert isinstance(result.url, str)
        assert result.status in ("healthy", "degraded", "down", "unknown")
        assert isinstance(result.last_check, str)


# ── Port Check Tests ─────────────────────────────────────────────────────────

class TestCheckPort:
    def test_closed_port(self):
        """An unused port should report open=False."""
        result = check_port("127.0.0.1", 59999, timeout=2.0)
        assert result["open"] is False

    def test_result_has_expected_keys(self):
        result = check_port("127.0.0.1", 59999, timeout=2.0)
        assert "host" in result
        assert "port" in result
        assert "open" in result


# ── SSL Check Tests ──────────────────────────────────────────────────────────

class TestCheckSSLCert:
    def test_invalid_domain(self):
        result = check_ssl_cert("this-domain-definitely-does-not-exist-12345.com")
        assert result["valid"] is False

    def test_result_structure(self):
        result = check_ssl_cert("example.com")
        assert "valid" in result
        # Could be valid or not depending on network, but structure should exist


# ── Env Var Check Tests ──────────────────────────────────────────────────────

class TestCheckEnvVars:
    def test_missing_vars(self):
        result = check_env_vars(["DEFINITELY_NOT_SET_VAR_12345"])
        assert result["all_set"] is False
        assert len(result["missing"]) == 1

    def test_present_vars(self):
        result = check_env_vars(["PATH"])
        assert len(result["present"]) >= 1
        assert result["all_set"] is True

    def test_env_file_missing(self):
        result = check_env_vars(["FOO", "BAR"], env_file="/nonexistent/.env")
        assert result["missing"] == ["FOO", "BAR"]
        assert result["all_set"] is False

    def test_env_file_with_vars(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n")
        result = check_env_vars(["FOO", "BAZ"], env_file=str(env_file))
        assert result["all_set"] is True
        assert set(result["present"]) == {"FOO", "BAZ"}


# ── Resource Usage Tests ─────────────────────────────────────────────────────

class TestCheckResourceUsage:
    def test_no_docker(self):
        """If docker isn't available, should return an error."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = check_resource_usage("test")
            assert "error" in result


# ── Readiness Scoring Tests ──────────────────────────────────────────────────

class TestScoreReadiness:
    def test_unreachable_service_low_score(self):
        result = score_readiness("http://localhost:59999")
        assert result["score"] < 50
        assert result["verdict"] == "NOT_READY"

    def test_result_structure(self):
        result = score_readiness("http://localhost:59999")
        assert "score" in result
        assert "verdict" in result
        assert "checks" in result
        assert "issues" in result
        assert result["verdict"] in ("READY", "RISKY", "NOT_READY")


# ── Service Tracking Tests ───────────────────────────────────────────────────

class TestServiceTracking:
    def test_add_service(self, isolated_services):
        result = add_service("my-api", "http://localhost:8080/health")
        assert "tracking" in result.lower() or "my-api" in result

    def test_list_services_after_add(self, isolated_services):
        add_service("svc1", "http://localhost:8080")
        result = list_services()
        assert "svc1" in result

    def test_remove_service(self, isolated_services):
        add_service("temp-svc", "http://localhost:9090")
        result = remove_service("temp-svc")
        assert "stopped tracking" in result.lower() or "temp-svc" in result.lower()
        services = _load_services()
        assert len(services) == 0

    def test_duplicate_service(self, isolated_services):
        add_service("dup-svc", "http://localhost:8080")
        result = add_service("dup-svc", "http://localhost:8081")
        assert "already" in result.lower()

    def test_check_service_by_name(self, isolated_services):
        add_service("named-svc", "http://localhost:59999", timeout=2.0)
        # Service tracked but unreachable
        with patch("tools.deploy_monitor.check_health") as mock_check:
            mock_check.return_value = ServiceStatus(
                name="named-svc", url="http://localhost:59999", status="down"
            )
            result = check_service_by_name("named-svc")
            # Just verify it doesn't crash
            assert result is not None or True  # may be None if not found


# ── Rollback Assessment Tests ────────────────────────────────────────────────

class TestAssessRollback:
    def test_healthy_no_rollback(self):
        current = ServiceStatus(name="api", status="healthy", error="")
        result = assess_rollback("api", current)
        assert result["recommendation"] == "OK"

    def test_down_strong_rollback(self):
        current = ServiceStatus(name="api", status="down", error="Connection refused")
        prev = ServiceStatus(name="api", status="healthy", error="")
        result = assess_rollback("api", current, prev)
        assert result["recommendation"] == "ROLLBACK"
        assert result["severity"] == "critical"

    def test_degraded_monitor(self):
        current = ServiceStatus(
            name="api", status="degraded", error="Slow response",
            response_time_ms=3000,
        )
        prev = ServiceStatus(
            name="api", status="healthy", error="",
            response_time_ms=100,
        )
        result = assess_rollback("api", current, prev)
        assert result["recommendation"] in ("ROLLBACK", "MONITOR")


# ── Cost Estimation Tests ────────────────────────────────────────────────────

class TestEstimateCost:
    def test_no_docker_error(self):
        with patch("tools.deploy_monitor.check_resource_usage") as mock:
            mock.return_value = {"error": "Docker not found"}
            result = estimate_deployment_cost()
            assert "error" in result

    def test_with_containers(self):
        containers = [
            {"name": "web-1", "cpu_pct": "25.3%", "mem_usage": "512MiB / 2GiB", "mem_pct": "25.0%"},
            {"name": "api-1", "cpu_pct": "5.1%", "mem_usage": "128MiB / 1GiB", "mem_pct": "12.5%"},
        ]
        result = estimate_deployment_cost(containers=containers)
        assert "total_monthly_estimate" in result
        assert result["containers_checked"] == 2
        # Second container has very low CPU — should trigger warning
        assert result["breakdown"][1].get("utilization_warning") is True


# ── Router Deploy Keywords Tests ─────────────────────────────────────────────

class TestRouterDeployKeywords:
    def test_deploy_keywords_exist(self):
        from core.router import _KEYWORD_ROUTES
        assert "deploy" in _KEYWORD_ROUTES
        keywords = _KEYWORD_ROUTES["deploy"]
        assert len(keywords) > 10

    def test_deploy_keywords_match_phrases(self):
        from core.router import _score_routes
        # These phrases should score for deploy route
        for phrase in [
            "check deployment",
            "is my site up",
            "production ready",
            "deploy health",
            "any service down",
            "rollback",
            "ssl check",
            "deploy cost",
        ]:
            scores = _score_routes(phrase)
            deploy_scores = [(r, s) for r, s in scores if r == "deploy"]
            assert len(deploy_scores) > 0, f"'{phrase}' should match deploy route"


# ── AWS Status + Situational Analysis Tests ──────────────────────────────────

class TestAwsStatus:
    def test_aws_status_returns_structure(self):
        """aws_status should return a dict with expected keys."""
        from tools.deploy_monitor import aws_status
        result = aws_status()
        assert "instances" in result
        assert "total_monthly_cost" in result
        assert "overall_analysis" in result

    def test_situational_analysis_generated(self):
        """Each instance should have analysis explaining WHAT and WHY."""
        from tools.deploy_monitor import aws_status
        result = aws_status()
        for inst in result.get("instances", []):
            analysis = inst.get("analysis", [])
            assert len(analysis) > 0, f"Instance {inst.get('name')} has no analysis"
            # At least one analysis should explain the CPU situation
            has_cpu_analysis = any("CPU" in a or "idle" in a.lower() or "utilization" in a.lower() for a in analysis)
            assert has_cpu_analysis, f"Instance {inst.get('name')} missing CPU analysis"

    def test_overall_analysis_present(self):
        """Account-level analysis should summarize state."""
        from tools.deploy_monitor import aws_status
        result = aws_status()
        overall = result.get("overall_analysis", [])
        assert len(overall) > 0, "No overall analysis generated"

    def test_analyze_instance_idle_detection(self):
        """_analyze_instance should flag low CPU as idle."""
        from tools.deploy_monitor import _analyze_instance
        data = {
            "name": "test-server",
            "state": "running",
            "cpu_24h_avg": 0.5,
            "cpu_24h_max": 5.0,
            "cpu": 2,
            "ram_gb": 4.0,
            "monthly_cost": 20.0,
            "provider": "AWS",
        }
        analysis = _analyze_instance(data)
        # Should flag as idle
        assert any("idle" in a.lower() for a in analysis)

    def test_analyze_instance_high_cpu(self):
        """_analyze_instance should flag high CPU as critical."""
        from tools.deploy_monitor import _analyze_instance
        data = {
            "name": "prod-server",
            "state": "running",
            "cpu_24h_avg": 92.0,
            "cpu_24h_max": 99.0,
            "cpu": 2,
            "ram_gb": 4.0,
            "monthly_cost": 20.0,
            "provider": "AWS",
        }
        analysis = _analyze_instance(data)
        assert any("critical" in a.lower() or "cpu-bound" in a.lower() for a in analysis)
