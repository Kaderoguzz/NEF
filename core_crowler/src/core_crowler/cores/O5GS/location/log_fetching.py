import docker
import time

from core_crowler.utils.logger import setup_logger
import subprocess

logger = setup_logger(logger_name="amf_log_watcher")

class DockerLogFetcher:
    def __init__(self, container_name: str, poll_interval: int = 2):
        self.container_name = container_name
        self.poll_interval = poll_interval
        self.use_sdk = True

        if docker:
            try:
                self.client = docker.from_env()
                self.container = self.client.containers.get(container_name)
                self.use_sdk = True
                logger.info("[INFO] Docker SDK initialized.")
            except Exception as e:
                logger.warning(f"[WARN] Docker SDK failed: {e}. Falling back to CLI.")
        else:
            logger.warning("[WARN] Docker SDK not available. Falling back to CLI.")

    def _stream_logs_sdk(self, on_line_bytes):
        stream = self.container.logs(
            stdout=True,
            stderr=True,
            follow=True,
            stream=True,
            tail=0,
            timestamps=False
        )

        buf = b""
        for chunk in stream:
            if not chunk:
                continue

            buf += chunk
            lines = buf.split(b"\n")

            # keep last partial line (if any)
            buf = lines.pop()

            for line in lines:
                on_line_bytes(line + b"\n")

    def _stream_logs_cli(self, on_line_bytes):
        cmd = ["docker", "logs", "--follow", "--tail", "0", self.container_name]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        try:
            for raw in iter(proc.stdout.readline, b""):
                if raw:
                    on_line_bytes(raw)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
    def run(self, on_line_bytes):
        """
        Runs forever, streaming logs. If the container restarts / connection breaks,
        we reconnect with a small sleep. Stale protection is handled in LogParser via ueLocationTimestamp.
        """
        logger.info("[INFO] Watching container '%s' logs...", self.container_name)

        while True:
            try:
                if self.use_sdk:
                    self._stream_logs_sdk(on_line_bytes)
                else:
                    self._stream_logs_cli(on_line_bytes)

            except Exception as e:
                logger.exception("[WARN] Log stream interrupted: %s. Reconnecting in %ds...", e, self.poll_interval)
                time.sleep(self.poll_interval)

                if self.use_sdk:
                    try:
                        self.container = self.client.containers.get(self.container_name)
                    except Exception as e2:
                        logger.warning("[WARN] Failed to re-acquire container: %s", e2)
                        self.use_sdk = False