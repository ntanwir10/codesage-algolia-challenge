"""
Performance monitoring service for CodeSage operations.
Tracks processing times, memory usage, and throughput metrics.
"""

import itertools
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import psutil
import structlog

logger = structlog.get_logger()

MAX_HISTORY = 1000
MAX_SAMPLES_PER_OPERATION = 200

# Prime psutil's non-blocking CPU counter; the first call returns a meaningless 0.0
psutil.cpu_percent(interval=None)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a single operation"""

    operation_name: str
    start_time: float
    end_time: float | None = None
    duration: float | None = None
    memory_start: float | None = None
    memory_end: float | None = None
    memory_peak: float | None = None
    items_processed: int = 0
    errors_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def finalize(self):
        """Finalize metrics calculation"""
        if self.end_time and self.start_time:
            self.duration = self.end_time - self.start_time
        if self.memory_start and self.memory_end:
            self.memory_peak = max(
                self.memory_start, self.memory_end, self.memory_peak or 0
            )

    @property
    def throughput(self) -> float:
        """Items processed per second"""
        if self.duration and self.duration > 0:
            return self.items_processed / self.duration
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/storage"""
        return {
            "operation": self.operation_name,
            "duration_seconds": self.duration,
            "items_processed": self.items_processed,
            "throughput_per_second": self.throughput,
            "memory_mb": {
                "start": self.memory_start,
                "end": self.memory_end,
                "peak": self.memory_peak,
            },
            "errors": self.errors_count,
            "metadata": self.metadata,
        }


class PerformanceMonitor:
    """
    Performance monitoring service for CodeSage operations.
    Tracks repository processing, GitHub API calls, Algolia operations, etc.
    """

    def __init__(self):
        self.metrics_history: deque[PerformanceMetrics] = deque(maxlen=MAX_HISTORY)
        self.active_operations: dict[str, PerformanceMetrics] = {}
        self.operation_stats: defaultdict[str, deque[PerformanceMetrics]] = (
            defaultdict(lambda: deque(maxlen=MAX_SAMPLES_PER_OPERATION))
        )
        self._counter = itertools.count(1)
        self._process = psutil.Process()

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            return self._process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    @asynccontextmanager
    async def monitor_operation(
        self, operation_name: str, metadata: dict[str, Any] | None = None
    ):
        """Context manager for monitoring an operation"""
        operation_id = f"{operation_name}_{next(self._counter)}"

        # Start monitoring
        metrics = PerformanceMetrics(
            operation_name=operation_name,
            start_time=time.time(),
            memory_start=self._get_memory_usage(),
            metadata=metadata or {},
        )

        self.active_operations[operation_id] = metrics

        try:
            logger.info(f"🚀 Starting operation: {operation_name}", **metrics.metadata)
            yield metrics

        except Exception as e:
            metrics.errors_count += 1
            metrics.metadata["error"] = str(e)
            # The operation's owner logs the failure; this only records the timing
            logger.warning(f"❌ Operation failed: {operation_name}", error=str(e))
            raise

        finally:
            # Finalize metrics
            metrics.end_time = time.time()
            metrics.memory_end = self._get_memory_usage()
            metrics.finalize()

            # Store metrics
            self.metrics_history.append(metrics)
            self.operation_stats[operation_name].append(metrics)
            self.active_operations.pop(operation_id, None)

            # Log completion
            logger.info(
                f"✅ Operation completed: {operation_name}",
                duration=f"{metrics.duration:.2f}s",
                throughput=(
                    f"{metrics.throughput:.1f}/s" if metrics.throughput > 0 else "N/A"
                ),
                memory_mb=f"{metrics.memory_end:.1f}MB",
                items=metrics.items_processed,
            )

    def get_operation_summary(self, operation_name: str) -> dict[str, Any]:
        """Get performance summary for an operation type"""
        ops = self.operation_stats.get(operation_name, [])
        if not ops:
            return {"operation": operation_name, "count": 0}

        durations = [op.duration for op in ops if op.duration]
        throughputs = [op.throughput for op in ops if op.throughput > 0]

        return {
            "operation": operation_name,
            "count": len(ops),
            "total_items_processed": sum(op.items_processed for op in ops),
            "total_errors": sum(op.errors_count for op in ops),
            "duration": {
                "min": min(durations) if durations else 0,
                "max": max(durations) if durations else 0,
                "avg": sum(durations) / len(durations) if durations else 0,
            },
            "throughput": {
                "min": min(throughputs) if throughputs else 0,
                "max": max(throughputs) if throughputs else 0,
                "avg": sum(throughputs) / len(throughputs) if throughputs else 0,
            },
            "success_rate": (
                (len(ops) - sum(op.errors_count for op in ops)) / len(ops) * 100
                if ops
                else 0
            ),
        }

    def get_system_metrics(self) -> dict[str, Any]:
        """Get current system performance metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "cpu_percent": cpu_percent,
                "memory": {
                    "total_gb": memory.total / 1024**3,
                    "available_gb": memory.available / 1024**3,
                    "used_percent": memory.percent,
                },
                "disk": {
                    "total_gb": disk.total / 1024**3,
                    "free_gb": disk.free / 1024**3,
                    "used_percent": (disk.used / disk.total) * 100,
                },
                "process": {
                    "memory_mb": self._get_memory_usage(),
                    "threads": self._process.num_threads(),
                },
            }
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {}

    def get_performance_report(
        self, system_metrics: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Generate comprehensive performance report"""
        operations_summary = {}
        for op_name in list(self.operation_stats):
            operations_summary[op_name] = self.get_operation_summary(op_name)

        return {
            "timestamp": time.time(),
            "active_operations": len(self.active_operations),
            "total_operations": len(self.metrics_history),
            "operations_summary": operations_summary,
            "system_metrics": (
                system_metrics if system_metrics is not None else self.get_system_metrics()
            ),
            "recent_operations": [
                op.to_dict() for op in list(self.metrics_history)[-10:]
            ],
        }

    def reset_metrics(self):
        """Reset all performance metrics"""
        self.metrics_history.clear()
        self.operation_stats.clear()
        logger.info("🔄 Performance metrics reset")


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Convenience functions
def monitor_repository_processing(repo_name: str | int, file_count: int = 0):
    """Monitor repository processing (use with `async with`)"""
    return performance_monitor.monitor_operation(
        "repository_processing",
        metadata={"repo_name": repo_name, "file_count": file_count},
    )
