import os
import time
from core_crowler.utils.logger import setup_logger


logger = setup_logger(logger_name = "amf_log_simulator")
class FileLogSimulator:
    def __init__(self, filepath: str, poll_interval: int = 2):
        self.filepath = filepath
        self.poll_interval = poll_interval
        self.offset = 0
        self.inode = None
        self.partial = b""

    def run_polling_loop(self, on_line_bytes):
        logger.info("Polling %s every %ds", self.filepath, self.poll_interval)

        while True:
            try:
                stat = os.stat(self.filepath)

                # File replaced (docker cp, rotation)
                if self.inode is None or stat.st_ino != self.inode:
                    logger.info("Log file replaced — resetting offset")
                    self.offset = 0
                    self.partial = b""
                    self.inode = stat.st_ino

                # File truncated
                if stat.st_size < self.offset:
                    logger.info("Log truncated — resetting offset")
                    self.offset = 0
                    self.partial = b""

                with open(self.filepath, "rb") as f:
                    logger.info("Starting reading file")
                    f.seek(self.offset)
                    data = f.read()
                    self.offset = f.tell()
                    logger.info("All bytes has been read")

                if data:
                    self._emit_lines(data, on_line_bytes)

            except FileNotFoundError:
                logger.warning("Log file not found — waiting")

            time.sleep(self.poll_interval)

    def _emit_lines(self, data: bytes, on_line_bytes) -> None:
        data = self.partial + data
        lines = data.splitlines()

        if not data.endswith(b"\n"):
            self.partial = lines.pop()
        else:
            self.partial = b""

        for line in lines:
            on_line_bytes(line + b"\n")
