from typing import Dict, Any

class RiskEngine:
    def __init__(self):
        self.WEIGHTS = {
            "geo": 0.35,
            "mobility": 0.50,   # mobility ağırlığı artırıldı
            "subscription": 0.15
        }

    def evaluate(self,
                 geo_result: Dict[str, Any],
                 mobility_result: Dict[str, Any],
                 subscription_result: Dict[str, Any]):
        geo_risk = geo_result.get("risk", 0)
        mobility_risk = mobility_result.get("risk", 0)
        sub_risk = subscription_result.get("risk", 0)

        final_score = (
            geo_risk * self.WEIGHTS["geo"] +
            mobility_risk * self.WEIGHTS["mobility"] +
            sub_risk * self.WEIGHTS["subscription"]
        )
        final_score = min(final_score, 100)

        # IMPOSSIBLE_TRAVEL varsa direkt BLOCK
        all_anomalies = (
            geo_result.get("anomalies", []) +
            mobility_result.get("anomalies", []) +
            subscription_result.get("anomalies", [])
        )
        if "IMPOSSIBLE_TRAVEL_DETECTED" in all_anomalies:
            final_score = max(final_score, 80)

        if final_score >= 75:
            decision = "BLOCK"
        elif final_score >= 45:
            decision = "CHALLENGE"
        else:
            decision = "ALLOW"

        return {
            "risk_score": round(final_score, 2),
            "decision": decision,
            "anomalies": list(set(all_anomalies)),
            "breakdown": {
                "geo": geo_risk,
                "mobility": mobility_risk,
                "subscription": sub_risk
            }
        }
