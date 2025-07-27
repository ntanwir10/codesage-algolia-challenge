"""
Performance monitoring service for CodeSage operations.
Tracks processing times, memory usage, and throughput metrics.
"""

import time
import asyncio
import psutil
import structlog
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from collections import defaultdict
import json

logger = structlog.get_logger()


@dataclass
class PerformanceMetrics:
    """Performance metrics for a single operation"""

    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    memory_start: Optional[float] = None
    memory_end: Optional[float] = None
    memory_peak: Optional[float] = None
    items_processed: int = 0
    errors_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

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

    def to_dict(self) -> Dict[str, Any]:
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
        self.metrics_history: List[PerformanceMetrics] = []
        self.active_operations: Dict[str, PerformanceMetrics] = {}
        self.operation_stats = defaultdict(list)
        self._process = psutil.Process()

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            return self._process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    @asynccontextmanager
    async def monitor_operation(
        self, operation_name: str, metadata: Optional[Dict[str, Any]] = None
    ):
        """Context manager for monitoring an operation"""
        operation_id = f"{operation_name}_{int(time.time() * 1000)}"

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
            logger.error(f"❌ Operation failed: {operation_name}", error=str(e))
            raise

        finally:
            # Finalize metrics
            metrics.end_time = time.time()
            metrics.memory_end = self._get_memory_usage()
            metrics.finalize()

            # Store metrics
            self.metrics_history.append(metrics)
            self.operation_stats[operation_name].append(metrics)
            del self.active_operations[operation_id]

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

    def get_operation_summary(self, operation_name: str) -> Dict[str, Any]:
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

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system performance metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
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

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        operations_summary = {}
        for op_name in self.operation_stats.keys():
            operations_summary[op_name] = self.get_operation_summary(op_name)

        return {
            "timestamp": time.time(),
            "active_operations": len(self.active_operations),
            "total_operations": len(self.metrics_history),
            "operations_summary": operations_summary,
            "system_metrics": self.get_system_metrics(),
            "recent_operations": [
                op.to_dict() for op in self.metrics_history[-10:]  # Last 10 operations
            ],
        }

    def reset_metrics(self):
        """Reset all performance metrics"""
        self.metrics_history.clear()
        self.operation_stats.clear()
        logger.info("🔄 Performance metrics reset")

    def export_metrics(self, filepath: str):
        """Export metrics to JSON file"""
        try:
            report = self.get_performance_report()
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"📊 Metrics exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Convenience functions
async def monitor_repository_processing(repo_name: str, file_count: int):
    """Monitor repository processing operation"""
    return performance_monitor.monitor_operation(
        "repository_processing",
        metadata={"repo_name": repo_name, "file_count": file_count},
    )


async def monitor_github_api_call(endpoint: str):
    """Monitor GitHub API call"""
    return performance_monitor.monitor_operation(
        "github_api_call", metadata={"endpoint": endpoint}
    )


async def monitor_algolia_indexing(index_name: str, item_count: int):
    """Monitor Algolia indexing operation"""
    return performance_monitor.monitor_operation(
        "algolia_indexing",
        metadata={"index_name": index_name, "item_count": item_count},
    )


async def monitor_code_parsing(language: str, file_count: int):
    """Monitor code parsing operation"""
    return performance_monitor.monitor_operation(
        "code_parsing", metadata={"language": language, "file_count": file_count}
    )
