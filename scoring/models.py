"""Shared data models for the scoring layer."""

from dataclasses import dataclass, field


@dataclass
class PointResult:
    point_number: int
    label: str
    score: str          # "strong" | "average" | "weak" | "unavailable"
    numeric: int        # 2 | 1 | 0
    rationale: str
    key_signals: list[str] = field(default_factory=list)
    data_used: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "point_number": self.point_number,
            "label":        self.label,
            "score":        self.score,
            "numeric":      self.numeric,
            "rationale":    self.rationale,
            "key_signals":  self.key_signals,
            "data_used":    self.data_used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PointResult":
        return cls(
            point_number=d["point_number"],
            label=d["label"],
            score=d["score"],
            numeric=d["numeric"],
            rationale=d["rationale"],
            key_signals=d.get("key_signals", []),
            data_used=d.get("data_used", {}),
        )


@dataclass
class EvalSummary:
    ticker: str
    company_name: str
    results: list[PointResult]
    total: int
    max_score: int
    ratio: float
    verdict: str        # "BUY / ACCUMULATE" | "WATCHLIST" | "PASS"
    critical_weak: list[int] = field(default_factory=list)  # point numbers

    def to_dict(self) -> dict:
        return {
            "ticker":        self.ticker,
            "company_name":  self.company_name,
            "results":       [r.to_dict() for r in self.results],
            "total":         self.total,
            "max_score":     self.max_score,
            "ratio":         self.ratio,
            "verdict":       self.verdict,
            "critical_weak": self.critical_weak,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvalSummary":
        return cls(
            ticker=d["ticker"],
            company_name=d["company_name"],
            results=[PointResult.from_dict(r) for r in d.get("results", [])],
            total=d["total"],
            max_score=d["max_score"],
            ratio=d["ratio"],
            verdict=d["verdict"],
            critical_weak=d.get("critical_weak", []),
        )
