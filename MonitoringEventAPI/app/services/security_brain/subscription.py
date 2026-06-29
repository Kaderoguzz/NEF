import time
from collections import defaultdict, deque
from .utils import safe_get


class SubscriptionAnalyzer:

    def __init__(self):
        # msisdn -> event timestamps
        self.event_log = defaultdict(deque)

        # thresholds
        self.MAX_EVENTS_PER_MINUTE = 20
        self.MAX_EVENTS_PER_10_SECONDS = 8
        self.TIME_WINDOW_SEC = 60

    def analyze(self, event: dict):
        """
        event:
        {
            "msisdn": "...",
            "timestamp": "..."
        }
        """

        msisdn = safe_get(event, "msisdn")
        timestamp = safe_get(event, "timestamp")

        now = self._to_epoch(timestamp)

        anomalies = []
        risk = 0

        logs = self.event_log[msisdn]

        # -----------------------------
        # 1. CLEAN OLD EVENTS
        # -----------------------------
        while logs and now - logs[0] > self.TIME_WINDOW_SEC:
            logs.popleft()

        # -----------------------------
        # 2. ADD CURRENT EVENT
        # -----------------------------
        logs.append(now)

        count_1min = len(logs)

        # -----------------------------
        # 3. RATE LIMIT CHECK (1 min)
        # -----------------------------
        if count_1min > self.MAX_EVENTS_PER_MINUTE:
            risk += 70
            anomalies.append("FLOOD_WITHIN_1_MIN")

        # -----------------------------
        # 4. BURST CHECK (last 10 sec)
        # -----------------------------
        recent_10s = [t for t in logs if now - t <= 10]

        if len(recent_10s) > self.MAX_EVENTS_PER_10_SECONDS:
            risk += 80
            anomalies.append("BURST_TRAFFIC_DETECTED")

        return {
            "msisdn": msisdn,
            "risk": min(risk, 100),
            "anomalies": anomalies,
            "event_count_1min": count_1min
        }

    def _to_epoch(self, ts):
        """
        timestamp → epoch seconds
        """

        if ts is None:
            return time.time()

        if isinstance(ts, (int, float)):
            return ts

        try:
            return time.mktime(time.strptime(ts.replace("Z", ""), "%Y-%m-%dT%H:%M:%S"))
        except:
            return time.time()
