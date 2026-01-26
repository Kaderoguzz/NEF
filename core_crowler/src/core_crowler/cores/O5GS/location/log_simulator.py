import os
import time
from datetime import datetime, timedelta

from core_crowler.utils.log_fetcher_helper import load_logs
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

# class FileLogSimulator:
#     def __init__(self, filepath: str, poll_interval: int = 5):
#         self.filepath = filepath
#         self.poll_interval = poll_interval
#         self.logs = self.init_logs_from_log_file()  # (timestamp, line) tuples
#         if self.logs:
#             self.last_fetch_time = self.logs[0][0] - timedelta(microseconds=1)
#         else:
#             self.last_fetch_time = datetime.now()

#     def init_logs_from_log_file(self) -> list[tuple[datetime, str]]:
#         lines = []
#         with open(self.filepath, 'rb') as f:
#             for line_bytes in f:
#                 try:
#                     line = line_bytes.decode('utf-8')
#                     lines.append(line)
#                 except UnicodeDecodeError:
#                     continue
#         try:
#             logs = load_logs(lines)
#         except Exception:
#             logs = load_logs([])
#         return logs

#     def update_logs(self):
#       self.logs = self.init_logs_from_log_file()

#     def fetch_logs(self):
#         self.update_logs()
#         #now = self.last_fetch_time + timedelta(seconds=self.poll_interval)
#         now = datetime.now()
#         self.last_fetch_time = now - timedelta(seconds=self.poll_interval)
#         #print(self.last_fetch_time, now)
#         # correction on where the time window of logs is referenced. If there are logs then the last log processed is the last_fetch_time and no the current time.
#         #logs_in_window = [(ts,line) for (ts, line) in self.logs if self.last_fetch_time < ts <= now]
#         logs_in_window = [(ts,line) for (ts, line) in self.logs if self.last_fetch_time < ts <= now]
#         print(logs_in_window[0][0], logs_in_window[-1][0], now)
#         #if logs_in_window:
#         #    self.last_fetch_time = max(ts for ts, _  in logs_in_window)
#         #else:
#         #    self.last_fetch_time = now
#         return [line for _,line in logs_in_window]

#     def run_polling_loop(self, handler_fn):
#         logger.info("[SIM] Polling logs from file every %ds...", self.poll_interval)

#         while True:

#             if not self.logs:
#                 logger.warning("[SIM] No valid logs found yet — waiting for new entries...")
#                 time.sleep(self.poll_interval)
#                 continue  # Try again next cycle

#             try:
#                 # Process new logs since last fetch
#                 while self.last_fetch_time < self.logs[-1][0]:
#                     logs = self.fetch_logs()
#                     logger.info("last_fetch_time: %s, logs[-1][0]: %s", self.last_fetch_time, self.logs[-1][0])
#                     if logs:
#                         handler_fn(logs)
#                 #logger.info("Reach to EOF. Going to sleep for %ds...", self.poll_interval)
#                 #time.sleep(self.poll_interval)
#                 self.fetch_logs()
#             except IndexError:
#                 # In case logs become empty between iterations
#                 logger.warning("[SIM] No logs available — retrying...")
#                 time.sleep(self.poll_interval)
#                 continue
#             except Exception as e:
#                 logger.exception("[SIM] Unexpected error in polling loop: %s", e)
#                 time.sleep(self.poll_interval)


