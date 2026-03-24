"""Data models for Fundamental Analysis."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricRow:
    name: str
    value: Any          # raw number, already formatted for display
    score: float        # 0–10
    note: str = ""


@dataclass
class SectionScore:
    key: str            # "valuation" | "profitability" | "growth" | "health" | "earnings_quality"
    name: str
    score: float        # 0–10 weighted sub-score
    label: str          # "Strong" | "Good" | "Fair" | "Weak" | "Poor"
    weight: float       # fraction of composite
    metrics: list = field(default_factory=list)   # list[MetricRow]
    notes: list = field(default_factory=list)

    def to_dict(self):
        return {
            "key": self.key, "name": self.name, "score": self.score,
            "label": self.label, "weight": self.weight,
            "metrics": [{"name": m.name, "value": m.value, "score": m.score, "note": m.note}
                        for m in self.metrics],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        obj = cls(key=d["key"], name=d["name"], score=d["score"],
                  label=d["label"], weight=d["weight"], notes=d.get("notes", []))
        obj.metrics = [MetricRow(**m) for m in d.get("metrics", [])]
        return obj


@dataclass
class DCFScenario:
    name: str               # "Bear" | "Base" | "Bull"
    fcf_growth: float       # annual FCF growth rate used
    intrinsic_value: float  # per share
    margin_of_safety: float # (intrinsic - price) / intrinsic; positive = undervalued

    def to_dict(self):
        return {"name": self.name, "fcf_growth": self.fcf_growth,
                "intrinsic_value": self.intrinsic_value,
                "margin_of_safety": self.margin_of_safety}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class FundamentalResult:
    ticker: str
    company_name: str
    sector: str
    current_price: float

    # Five scored sections
    sections: dict = field(default_factory=dict)   # key → SectionScore

    # Weighted composite (0–10)
    composite_score: float = 0.0
    composite_label: str = "HOLD"
    recommendation: str = "HOLD"    # "BUY" | "HOLD" | "AVOID"

    # DCF
    dcf_scenarios: list = field(default_factory=list)   # list[DCFScenario]
    wacc: float = 0.09
    terminal_growth: float = 0.03

    # Dividend (None if company pays no dividends)
    dividend_metrics: dict = field(default_factory=dict)

    red_flags: list = field(default_factory=list)
    highlights: list = field(default_factory=list)

    def to_dict(self):
        return {
            "ticker": self.ticker, "company_name": self.company_name,
            "sector": self.sector, "current_price": self.current_price,
            "sections": {k: v.to_dict() for k, v in self.sections.items()},
            "composite_score": self.composite_score,
            "composite_label": self.composite_label,
            "recommendation": self.recommendation,
            "dcf_scenarios": [s.to_dict() for s in self.dcf_scenarios],
            "wacc": self.wacc, "terminal_growth": self.terminal_growth,
            "dividend_metrics": self.dividend_metrics,
            "red_flags": self.red_flags, "highlights": self.highlights,
        }

    @classmethod
    def from_dict(cls, d):
        obj = cls(
            ticker=d["ticker"], company_name=d["company_name"],
            sector=d["sector"], current_price=d["current_price"],
            composite_score=d["composite_score"],
            composite_label=d["composite_label"],
            recommendation=d["recommendation"],
            wacc=d.get("wacc", 0.09), terminal_growth=d.get("terminal_growth", 0.03),
            dividend_metrics=d.get("dividend_metrics", {}),
            red_flags=d.get("red_flags", []), highlights=d.get("highlights", []),
        )
        obj.sections = {k: SectionScore.from_dict(v) for k, v in d.get("sections", {}).items()}
        obj.dcf_scenarios = [DCFScenario.from_dict(s) for s in d.get("dcf_scenarios", [])]
        return obj
