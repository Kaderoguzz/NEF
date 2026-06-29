from .geo_analyzer import GeoAnalyzer
from .mobility import MobilityAnalyzer
from .subscription import SubscriptionAnalyzer
from .risk_engine import RiskEngine
from .utils import safe_get

class SecurityBrainAnalyzer:
    def __init__(self):
        self.geo_analyzer = GeoAnalyzer()
        self.mobility_analyzer = MobilityAnalyzer()
        self.subscription_analyzer = SubscriptionAnalyzer()
        self.risk_engine = RiskEngine()

    def analyze(self, event: dict, geo_db: dict = None):
        geo_db = geo_db or {}
        msisdn = safe_get(event, "msisdn")
        geo_result = self.geo_analyzer.analyze(event, geo_db)
        mobility_result = self.mobility_analyzer.analyze(event)
        subscription_result = self.subscription_analyzer.analyze(event)
        final_decision = self.risk_engine.evaluate(geo_result, mobility_result, subscription_result)
        return {
            "msisdn": msisdn,
            "analysis": {
                "geo": geo_result,
                "mobility": mobility_result,
                "subscription": subscription_result
            },
            "security": final_decision
        }
