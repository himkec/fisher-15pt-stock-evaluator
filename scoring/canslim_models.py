"""Data models for CAN SLIM analysis."""

from dataclasses import dataclass, field


@dataclass
class LetterScore:
    letter: str
    name: str
    score: float          # 0–100
    label: str            # "Strong" | "Average" | "Weak"
    weight: float         # weight in composite (0–1)
    metrics: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "letter": self.letter,
            "name": self.name,
            "score": self.score,
            "label": self.label,
            "weight": self.weight,
            "metrics": self.metrics,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LetterScore":
        return cls(
            letter=d["letter"],
            name=d["name"],
            score=d["score"],
            label=d["label"],
            weight=d.get("weight", 0.0),
            metrics=d.get("metrics", {}),
            notes=d.get("notes", []),
        )


@dataclass
class BuyPoint:
    pivot: float          # resistance level / 52-week high
    valid: bool           # True when near pivot on high volume
    entry: float          # pivot * 1.02
    stop_loss: float      # entry * 0.93 (–7%)
    take_profit: float    # entry * 1.25 (+25%)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "pivot": self.pivot,
            "valid": self.valid,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BuyPoint":
        return cls(
            pivot=d["pivot"],
            valid=d["valid"],
            entry=d["entry"],
            stop_loss=d["stop_loss"],
            take_profit=d["take_profit"],
            notes=d.get("notes", ""),
        )


@dataclass
class CANSLIMResult:
    ticker: str
    company_name: str

    # Composite (C + A + N + S + L + I weighted)
    composite_score: float    # 0–100
    composite_label: str      # "Strong" | "Average" | "Weak"

    # Per-letter scores (keys: "C","A","N","S","L","I")
    letter_scores: dict[str, LetterScore] = field(default_factory=dict)

    # Market direction gatekeeper (M — not in composite)
    market_direction: str = "mixed"   # "market_uptrend"|"mixed"|"market_correction"
    market_metrics: dict = field(default_factory=dict)

    # Technical buy point
    buy_point: BuyPoint | None = None

    # Decision
    recommendation: str = "WATCHLIST"   # "BUY" | "WATCHLIST" | "AVOID"
    red_flags: list[str] = field(default_factory=list)

    # Investor suitability
    investor_fit: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "composite_score": self.composite_score,
            "composite_label": self.composite_label,
            "letter_scores": {k: v.to_dict() for k, v in self.letter_scores.items()},
            "market_direction": self.market_direction,
            "market_metrics": self.market_metrics,
            "buy_point": self.buy_point.to_dict() if self.buy_point else None,
            "recommendation": self.recommendation,
            "red_flags": self.red_flags,
            "investor_fit": self.investor_fit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CANSLIMResult":
        obj = cls(
            ticker=d["ticker"],
            company_name=d["company_name"],
            composite_score=d["composite_score"],
            composite_label=d["composite_label"],
            market_direction=d.get("market_direction", "mixed"),
            market_metrics=d.get("market_metrics", {}),
            recommendation=d["recommendation"],
            red_flags=d.get("red_flags", []),
            investor_fit=d.get("investor_fit", {}),
        )
        obj.letter_scores = {
            k: LetterScore.from_dict(v)
            for k, v in d.get("letter_scores", {}).items()
        }
        bp = d.get("buy_point")
        obj.buy_point = BuyPoint.from_dict(bp) if bp else None
        return obj
