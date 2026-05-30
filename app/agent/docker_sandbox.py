"""Docker sandbox manager — per-user container lifecycle for code execution."""

import time
from app.config import settings
from app.middleware.error_handler import AppError
import logging

log = logging.getLogger(__name__)

_manager = None


def get_sandbox_manager() -> "DockerSandboxManager":
    global _manager
    if _manager is None:
        _manager = DockerSandboxManager()
    return _manager


class DockerSandboxManager:
    def __init__(self):
        self._client = None  # Lazy init — docker may not be available in dev
        self._user_containers: dict[str, list[str]] = {}
        self._last_activity: dict[str, float] = {}  # container_id -> timestamp

    def _ensure_client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except Exception:
                log.warning("Docker not available — sandbox tools will fail")
                raise AppError("BX_AGENT_7006", "Docker daemon not available", 503)

    def get_or_create(self, employee_id: int) -> str:
        """Get an existing idle container or create a new one for the user."""
        self._ensure_client()

        # Reuse existing idle container for the user
        existing = self._user_containers.get(employee_id, [])
        for cid in existing:
            try:
                container = self._client.containers.get(cid)
                if container.status == "running":
                    self._last_activity[cid] = time.time()
                    return cid
            except docker.errors.NotFound:
                existing.remove(cid)

        # Check global limit
        all_containers = self._client.containers.list(filters={"label": "bx-sandbox"})
        if len(all_containers) >= settings.docker_max_global_containers:
            self.cleanup_idle()
            all_containers = self._client.containers.list(filters={"label": "bx-sandbox"})
            if len(all_containers) >= settings.docker_max_global_containers:
                raise AppError("BX_AGENT_7004", "Global sandbox capacity reached", 429)

        # Check per-user limit
        user_count = len(self._user_containers.get(employee_id, []))
        if user_count >= settings.docker_max_containers_per_user:
            raise AppError("BX_AGENT_7005", "User sandbox limit reached", 429)

        container = self._client.containers.run(
            settings.docker_sandbox_image,
            detach=True,
            labels={"bx-sandbox": str(employee_id)},
            auto_remove=False,
            mem_limit="256m",
            cpu_period=100000,
            cpu_quota=50000,  # 50% of one core
            network_disabled=True,
        )
        cid = container.id
        self._user_containers.setdefault(employee_id, []).append(cid)
        self._last_activity[cid] = time.time()
        return cid

    async def execute_code(self, container_id: str, code: str) -> dict:
        """Execute code in a sandbox container, return output."""
        self._ensure_client()
        container = self._client.containers.get(container_id)
        self._last_activity[container_id] = time.time()
        exec_result = container.exec_run(code, workdir="/tmp")
        return {"exit_code": exec_result.exit_code, "output": exec_result.output.decode(errors="replace")}

    def cleanup_idle(self, idle_timeout_minutes: int = None):
        """Remove containers idle beyond the timeout."""
        if self._client is None:
            return
        timeout = idle_timeout_minutes or settings.docker_container_idle_timeout_minutes
        cutoff = time.time() - (timeout * 60)
        for cid, ts in list(self._last_activity.items()):
            if ts < cutoff:
                try:
                    container = self._client.containers.get(cid)
                    container.stop(timeout=5)
                    container.remove()
                except Exception:
                    pass
                self._last_activity.pop(cid, None)
                # Remove from user mapping
                for user, containers in self._user_containers.items():
                    if cid in containers:
                        containers.remove(cid)