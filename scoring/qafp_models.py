"""Data models for Quality at a Fair Price (QAFP) analysis."""

from dataclasses import dataclass, field


@dataclass
class SubScore:
    name: str
    score: float          # 0–100
    label: str            # "High" | "Above Average" | "Average" | "Low"
    metrics: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "score": self.score, "label": self.label,
                "metrics": self.metrics, "notes": self.notes}

    @classmethod
    def from_dict(cls, d: dict) -> "SubScore":
        return cls(name=d["name"], score=d["score"], label=d["label"],
                   metrics=d.get("metrics", {}), notes=d.get("notes", []))


@dataclass
class QAFPResult:
    ticker: str
    company_name: str
    security_type: str            # "stock" | "etf"
    sector: str

    # Scores
    quality_score: float          # 0–100
    quality_label: str            # "High" | "Above Average" | "Average" | "Low"
    valuation_score: float        # 0–100
    valuation_label: str          # "Cheap" | "Fair" | "Expensive"

    # Sub-scores
    sub_scores: dict[str, SubScore] = field(default_factory=dict)

    # Valuation details
    key_metrics: dict = field(default_factory=dict)
    valuation_metrics: dict = field(default_factory=dict)

    # Return heuristic
    expected_return: float = 0.0
    required_return: float = 0.09   # default 9%

    # Decision
    recommendation: str = "WATCHLIST"   # "BUY / ACCUMULATE" | "WATCHLIST" | "AVOID"
    red_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "security_type": self.security_type,
            "sector": self.sector,
            "quality_score": self.quality_score,
            "quality_label": self.quality_label,
            "valuation_score": self.valuation_score,
            "valuation_label": self.valuation_label,
            "sub_scores": {k: v.to_dict() for k, v in self.sub_scores.items()},
            "key_metrics": self.key_metrics,
            "valuation_metrics": self.valuation_metrics,
            "expected_return": self.expected_return,
            "required_return": self.required_return,
            "recommendation": self.recommendation,
            "red_flags": self.red_flags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QAFPResult":
        obj = cls(
            ticker=d["ticker"],
            company_name=d["company_name"],
            security_type=d["security_type"],
            sector=d["sector"],
            quality_score=d["quality_score"],
            quality_label=d["quality_label"],
            valuation_score=d["valuation_score"],
            valuation_label=d["valuation_label"],
            key_metrics=d.get("key_metrics", {}),
            valuation_metrics=d.get("valuation_metrics", {}),
            expected_return=d.get("expected_return", 0.0),
            required_return=d.get("required_return", 0.09),
            recommendation=d["recommendation"],
            red_flags=d.get("red_flags", []),
        )
        obj.sub_scores = {k: SubScore.from_dict(v) for k, v in d.get("sub_scores", {}).items()}
        return obj
