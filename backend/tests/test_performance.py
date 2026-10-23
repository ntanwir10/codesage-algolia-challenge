import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.performance_monitor import (
    MAX_HISTORY,
    PerformanceMonitor,
    monitor_code_parsing,
    monitor_repository_processing,
    performance_monitor,
)


@pytest.fixture(autouse=True)
def reset_global_monitor():
    performance_monitor.reset_metrics()
    yield
    performance_monitor.reset_metrics()


def test_system_metrics_does_not_block():
    monitor = PerformanceMonitor()
    start = time.perf_counter()
    metrics = monitor.get_system_metrics()
    assert time.perf_counter() - start < 0.2
    assert "cpu_percent" in metrics


async def test_history_is_bounded():
    monitor = PerformanceMonitor()
    for _ in range(MAX_HISTORY + 50):
        async with monitor.monitor_operation("op"):
            pass
    assert len(monitor.metrics_history) == MAX_HISTORY
    assert len(monitor.operation_stats["op"]) <= MAX_HISTORY
    assert monitor.active_operations == {}


async def test_concurrent_operations_do_not_collide():
    monitor = PerformanceMonitor()

    async def run():
        async with monitor.monitor_operation("same"):
            await asyncio.sleep(0.01)

    await asyncio.gather(*(run() for _ in range(20)))
    assert len(monitor.metrics_history) == 20
    assert monitor.active_operations == {}


async def test_nested_same_name_operations():
    monitor = PerformanceMonitor()
    async with monitor.monitor_operation("n"):
        async with monitor.monitor_operation("n"):
            assert len(monitor.active_operations) == 2
    assert len(monitor.metrics_history) == 2


async def test_monitor_helper_works_with_async_with():
    async with monitor_repository_processing(1) as metrics:
        metrics.items_processed = 5
    assert len(performance_monitor.metrics_history) == 1
    assert (
        performance_monitor.metrics_history[0].operation_name
        == "repository_processing"
    )
    summary = performance_monitor.get_operation_summary("repository_processing")
    assert summary["count"] == 1
    assert summary["total_items_processed"] == 5


async def test_failed_operation_recorded_and_cleaned_up():
    with pytest.raises(ValueError):
        async with monitor_code_parsing("python", 1):
            raise ValueError("bad")
    assert performance_monitor.active_operations == {}
    assert performance_monitor.metrics_history[0].errors_count == 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/performance/metrics",
        "/api/v1/performance/system",
        "/api/v1/performance/health-check",
        "/api/v1/performance/health",
        "/api/v1/performance/export",
    ],
)
def test_endpoints_return_200_quickly(path):
    client = TestClient(app)
    start = time.perf_counter()
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert time.perf_counter() - start < 0.5


def test_reset_and_operation_endpoints():
    client = TestClient(app)
    assert client.post("/api/v1/performance/reset").status_code == 200
    assert client.get("/api/v1/performance/operations/nope").status_code == 404


def test_health_computes_system_metrics_once(monkeypatch):
    calls = 0
    original = performance_monitor.get_system_metrics

    def counting():
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(performance_monitor, "get_system_metrics", counting)
    TestClient(app).get("/api/v1/performance/health-check")
    assert calls == 1
