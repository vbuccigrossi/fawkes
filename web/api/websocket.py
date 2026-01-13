"""
WebSocket Manager for Real-Time Updates

Manages WebSocket connections and broadcasts real-time updates
for system stats, job status, crashes, and worker status.
"""

import asyncio
import json
import logging
import time
from typing import Set, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

try:
    import psutil
except ImportError:
    psutil = None

from api.database import db_manager

logger = logging.getLogger("fawkes.web.websocket")


class SimpleResourceMonitor:
    """Simple resource monitor using psutil directly."""

    def get_stats(self) -> Dict[str, Any]:
        """Get system resource statistics."""
        if psutil is None:
            return {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "running_vms": 0,
                "max_vms": 10
            }

        # Count QEMU processes as VMs
        running_vms = 0
        try:
            for proc in psutil.process_iter(['name']):
                if 'qemu' in proc.info['name'].lower():
                    running_vms += 1
        except Exception:
            pass

        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "running_vms": running_vms,
            "max_vms": db_manager.config.get("max_vms", 10)
        }


class WebSocketManager:
    """Manages WebSocket connections and real-time broadcasts."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.subscriptions: Dict[WebSocket, Set[str]] = {}
        self.last_stats: Dict[str, Any] = {}
        self.resource_monitor = SimpleResourceMonitor()

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.subscriptions[websocket] = {"stats", "jobs", "crashes"}  # Default subscriptions
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        self.subscriptions.pop(websocket, None)
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def send_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send a message to a specific client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any], channel: str = None):
        """Broadcast a message to all subscribed clients."""
        disconnected = []
        for ws in list(self.active_connections):
            # Check if client is subscribed to this channel
            if channel and channel not in self.subscriptions.get(ws, set()):
                continue

            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(ws)

        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws)

    async def broadcast_loop(self):
        """Background task that broadcasts periodic updates."""
        logger.info("Starting WebSocket broadcast loop")

        while True:
            try:
                await asyncio.sleep(2)  # Update every 2 seconds

                if not self.active_connections:
                    continue  # No clients, skip

                # Get system stats
                system_stats = await self.get_system_stats()
                if system_stats != self.last_stats.get("system"):
                    await self.broadcast({
                        "type": "stats_update",
                        "data": system_stats
                    }, channel="stats")
                    self.last_stats["system"] = system_stats

                # Get job statuses
                job_stats = await self.get_job_stats()
                if job_stats != self.last_stats.get("jobs"):
                    await self.broadcast({
                        "type": "jobs_update",
                        "data": job_stats
                    }, channel="jobs")
                    self.last_stats["jobs"] = job_stats

                # Check for new crashes
                await self.check_new_crashes()

                # Get worker stats (controller mode only)
                if db_manager.mode == "controller":
                    worker_stats = await self.get_worker_stats()
                    if worker_stats != self.last_stats.get("workers"):
                        await self.broadcast({
                            "type": "workers_update",
                            "data": worker_stats
                        }, channel="workers")
                        self.last_stats["workers"] = worker_stats

            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Longer delay on error

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get current system statistics."""
        try:
            stats = self.resource_monitor.get_stats()

            # Add database stats
            db_stats = db_manager.get_stats()

            # Get config values for dashboard display
            config = db_manager.config

            return {
                "cpu_percent": stats.get("cpu_percent", 0.0),
                "memory_percent": stats.get("memory_percent", 0.0),
                "running_vms": stats.get("running_vms", 0),
                "max_vms": stats.get("max_vms", 0),
                "total_jobs": db_stats.get("total_jobs", 0),
                "running_jobs": db_stats.get("running_jobs", 0),
                "total_crashes": db_stats.get("total_crashes", 0),
                "unique_crashes": db_stats.get("unique_crashes", 0),
                "total_testcases": db_stats.get("total_testcases", 0),
                "timestamp": time.time(),
                # Config-based feature flags for dashboard display
                "time_compression_enabled": config.get("enable_time_compression", False),
                "persistent_mode_enabled": config.get("enable_persistent", False),
                "corpus_sync_enabled": config.get("enable_corpus_sync", False),
                "stack_dedup_enabled": config.get("enable_stack_deduplication", False),
            }
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            return {}

    async def get_job_stats(self) -> Dict[int, Dict[str, Any]]:
        """Get statistics for all active jobs."""
        try:
            jobs = db_manager.get_jobs()
            job_stats = {}

            for job in jobs:
                job_id = job.get("job_id")
                job_stats[job_id] = {
                    "job_id": job_id,
                    "name": job.get("name", "Unnamed"),
                    "status": job.get("status", "unknown"),
                    "testcases": job.get("total_testcases", 0),
                    "crashes": len(db_manager.get_crashes(job_id=job_id))
                }

            return job_stats
        except Exception as e:
            logger.error(f"Error getting job stats: {e}")
            return {}

    async def get_worker_stats(self) -> Dict[int, Dict[str, Any]]:
        """Get statistics for all workers (controller mode only)."""
        try:
            workers = db_manager.get_workers()
            worker_stats = {}

            for worker in workers:
                worker_id = worker.get("worker_id")
                worker_stats[worker_id] = {
                    "worker_id": worker_id,
                    "ip_address": worker.get("ip_address"),
                    "status": worker.get("status", "unknown"),
                    "last_seen": worker.get("last_seen")
                }

            return worker_stats
        except Exception as e:
            logger.error(f"Error getting worker stats: {e}")
            return {}

    async def check_new_crashes(self):
        """Check for new crashes and broadcast them."""
        try:
            crashes = db_manager.get_crashes()

            # Track last known crash ID
            if not hasattr(self, 'last_crash_id'):
                self.last_crash_id = max([c.get("crash_id", 0) for c in crashes], default=0)
                return

            # Find new crashes
            new_crashes = [c for c in crashes if c.get("crash_id", 0) > self.last_crash_id]

            for crash in new_crashes:
                await self.broadcast({
                    "type": "new_crash",
                    "data": {
                        "crash_id": crash.get("crash_id"),
                        "job_id": crash.get("job_id"),
                        "crash_type": crash.get("crash_type"),
                        "severity": crash.get("severity"),
                        "sanitizer_type": crash.get("sanitizer_type"),
                        "timestamp": crash.get("timestamp"),
                        "is_unique": crash.get("is_unique", True)
                    }
                }, channel="crashes")

                self.last_crash_id = crash.get("crash_id", self.last_crash_id)

        except Exception as e:
            logger.error(f"Error checking new crashes: {e}")


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint handler."""
    await websocket_manager.connect(websocket)

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "subscribe":
                # Add channels to subscription
                channels = message.get("channels", [])
                websocket_manager.subscriptions[websocket].update(channels)
                await websocket_manager.send_message(websocket, {
                    "type": "subscribed",
                    "channels": list(websocket_manager.subscriptions[websocket])
                })

            elif msg_type == "unsubscribe":
                # Remove channels from subscription
                channels = message.get("channels", [])
                websocket_manager.subscriptions[websocket].difference_update(channels)
                await websocket_manager.send_message(websocket, {
                    "type": "unsubscribed",
                    "channels": list(websocket_manager.subscriptions[websocket])
                })

            elif msg_type == "ping":
                # Heartbeat
                await websocket_manager.send_message(websocket, {
                    "type": "pong",
                    "timestamp": time.time()
                })

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        websocket_manager.disconnect(websocket)
