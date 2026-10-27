"""
Performance monitoring API endpoints.
Provides real-time performance metrics and system monitoring.
"""

import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.performance_monitor import performance_monitor

logger = structlog.get_logger()
router = APIRouter()


class PerformanceReportResponse(BaseModel):
    """Response model for performance reports"""

    timestamp: float
    active_operations: int
    total_operations: int
    operations_summary: dict[str, Any]
    system_metrics: dict[str, Any]
    recent_operations: list


@router.get(
    "/metrics",
    response_model=PerformanceReportResponse,
    summary="Get Performance Metrics",
    description="Get comprehensive performance metrics including system stats and operation summaries",
)
async def get_performance_metrics():
    """
    Get current performance metrics for CodeSage operations.

    Returns system metrics, operation summaries, and recent operation history.
    """
    try:
        report = performance_monitor.get_performance_report()
        return PerformanceReportResponse(**report)
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve performance metrics"
        ) from e


@router.get(
    "/operations/{operation_name}",
    summary="Get Operation Performance",
    description="Get detailed performance metrics for a specific operation type",
)
async def get_operation_performance(operation_name: str):
    """
    Get performance metrics for a specific operation type.

    Args:
        operation_name: Name of the operation; 'repository_processing' is the one recorded
    """
    try:
        summary = performance_monitor.get_operation_summary(operation_name)
        if summary["count"] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No metrics found for operation: {operation_name}",
            )
        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get operation performance for {operation_name}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve operation metrics"
        ) from e


@router.get(
    "/system",
    summary="Get System Metrics",
    description="Get current system performance metrics (CPU, memory, disk)",
)
async def get_system_metrics():
    """
    Get current system performance metrics.

    Returns CPU usage, memory statistics, disk usage, and process information.
    """
    try:
        metrics = performance_monitor.get_system_metrics()
        if not metrics:
            raise HTTPException(
                status_code=500, detail="Unable to retrieve system metrics"
            )
        return metrics
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system metrics") from e


@router.post(
    "/reset",
    summary="Reset Performance Metrics",
    description="Reset all performance metrics and operation history",
)
async def reset_performance_metrics():
    """
    Reset all performance metrics.

    Clears operation history and metrics but keeps system monitoring active.
    """
    try:
        performance_monitor.reset_metrics()
        return {
            "message": "Performance metrics reset successfully",
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Failed to reset performance metrics: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to reset performance metrics"
        ) from e


@router.get("/health", include_in_schema=False)
@router.get(
    "/health-check",
    summary="Performance Health Check",
    description="Quick health check with key performance indicators",
)
async def performance_health_check():
    """
    Quick performance health check.

    Returns key indicators to assess if the system is performing well.
    """
    try:
        system_metrics = performance_monitor.get_system_metrics()

        # Determine health status based on system metrics
        health_status = "healthy"
        warnings = []

        if system_metrics.get("cpu_percent", 0) > 80:
            health_status = "warning"
            warnings.append("High CPU usage")

        if system_metrics.get("memory", {}).get("used_percent", 0) > 85:
            health_status = "warning"
            warnings.append("High memory usage")

        if system_metrics.get("disk", {}).get("used_percent", 0) > 90:
            health_status = "critical"
            warnings.append("Disk space critical")

        active_ops = len(performance_monitor.active_operations)
        if active_ops > 10:
            health_status = "warning"
            warnings.append(f"High number of active operations ({active_ops})")

        return {
            "status": health_status,
            "warnings": warnings,
            "active_operations": active_ops,
            "system_summary": {
                "cpu_percent": system_metrics.get("cpu_percent", 0),
                "memory_used_percent": system_metrics.get("memory", {}).get(
                    "used_percent", 0
                ),
                "disk_used_percent": system_metrics.get("disk", {}).get(
                    "used_percent", 0
                ),
                "process_memory_mb": system_metrics.get("process", {}).get(
                    "memory_mb", 0
                ),
            },
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Performance health check failed: {e}")
        raise HTTPException(status_code=500, detail="Performance health check failed") from e


@router.get(
    "/export",
    summary="Export Performance Metrics",
    description="Export performance metrics to a downloadable format",
)
async def export_performance_metrics(
    format: str = Query("json", description="Export format (json)")
):
    """
    Export performance metrics for analysis.

    Args:
        format: Export format, currently supports 'json'
    """
    try:
        if format.lower() != "json":
            raise HTTPException(
                status_code=400, detail="Only JSON format is currently supported"
            )

        report = performance_monitor.get_performance_report()

        # Add export metadata
        export_data = {
            "export_timestamp": report["timestamp"],
            "export_format": "json",
            "codesage_version": "1.0.0",
            "performance_data": report,
        }

        return export_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export performance metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to export metrics") from e
