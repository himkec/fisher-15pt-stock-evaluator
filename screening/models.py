"""
Data models for the Quality-First Fundamental Screen.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QualityScreenConfig:
    """User-configurable thresholds.  Defaults match the requirements doc."""
    # Universe
    sector_filter: str   = "All Sectors"   # "All Sectors" or a GICS sector name
    min_market_cap_b: float = 1.0

    # Step 2 — Profitability
    min_roic_5y: float  = 0.15   # 5-year avg ROIC
    min_op_margin_5y: float = 0.10   # 5-year avg operating margin
    min_fcf_margin_5y: float = 0.10  # 5-year avg FCF / Revenue
    min_fcf_positive_years: int = 4  # must be FCF-positive in ≥ N of last 5 years

    # Step 3 — Balance sheet
    max_net_debt_ebitda: float = 3.0   # net debt / EBITDA (use 99 for net-cash)
    min_interest_coverage: float = 3.5  # EBIT / interest expense
    max_share_dilution_5y: float = 0.15 # total share-count growth over 5 yrs (fractional)

    # Step 4 — Earnings quality
    min_cfo_ni_ratio: float = 0.70     # cumulative CFO / cumulative net income over 5Y
    max_eps_vol_pct: float  = 0.70     # keep bottom 70% least-volatile (drop top 30%)

    # Step 5 — Scoring weights (must sum to 1.0)
    w_roic: float = 0.25
    w_fcf_margin: float = 0.20
    w_op_margin: float = 0.15
    w_leverage: float = 0.20   # higher rank = lower leverage
    w_volatility: float = 0.10  # higher rank = lower EPS volatility
    w_cash_conv: float = 0.10   # higher rank = better CFO/NI

    def cache_key(self) -> str:
        sector = self.sector_filter.replace(" ", "_")
        return (
            f"screen:quality:{sector}:"
            f"r{self.min_roic_5y:.2f}_o{self.min_op_margin_5y:.2f}_"
            f"f{self.min_fcf_margin_5y:.2f}_d{self.max_net_debt_ebitda:.1f}_"
            f"ic{self.min_interest_coverage:.1f}_cni{self.min_cfo_ni_ratio:.2f}"
        )

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "QualityScreenConfig":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class StockScreenMetrics:
    """Quality metrics computed for one stock."""
    ticker: str
    name: str
    sector: str

    # ── Raw metrics ──────────────────────────────────────────────────────────
    market_cap_b: float = 0.0

    # Profitability (Step 2)
    roic_5y: float = 0.0
    op_margin_5y: float = 0.0
    fcf_margin_5y: float = 0.0
    fcf_positive_years: int = 0

    # Balance sheet (Step 3)
    net_debt_ebitda: float = 0.0
    interest_coverage: float = 0.0
    share_dilution_5y: float = 0.0  # positive = dilution

    # Earnings quality (Step 4)
    eps_growth_vol: float = 0.0   # std dev of annual EPS growth rates
    cfo_ni_ratio: float = 0.0

    # ── Filter result ─────────────────────────────────────────────────────────
    passed: bool = False
    fail_step: str = ""       # "profitability" | "balance_sheet" | "earnings_quality" | ""
    fail_reason: str = ""

    # ── Composite score (Step 5) ──────────────────────────────────────────────
    roic_pct: float = 0.0
    fcf_margin_pct: float = 0.0
    op_margin_pct: float = 0.0
    leverage_pct: float = 0.0
    volatility_pct: float = 0.0
    cash_conv_pct: float = 0.0
    quality_score: float = 0.0   # 0–100 composite

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "StockScreenMetrics":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class QualityScreenResult:
    """Full output of one screen run."""
    config: QualityScreenConfig
    run_date: str
    universe_size: int
    after_profitability: int
    after_balance_sheet: int
    after_earnings_quality: int
    survivors: list = field(default_factory=list)   # list[StockScreenMetrics], ranked
    all_metrics: list = field(default_factory=list)  # list[StockScreenMetrics], full universe
    run_seconds: float = 0.0
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "config":               self.config.to_dict(),
            "run_date":             self.run_date,
            "universe_size":        self.universe_size,
            "after_profitability":  self.after_profitability,
            "after_balance_sheet":  self.after_balance_sheet,
            "after_earnings_quality": self.after_earnings_quality,
            "survivors":            [s.to_dict() for s in self.survivors],
            "all_metrics":          [s.to_dict() for s in self.all_metrics],
            "run_seconds":          self.run_seconds,
            "errors":               self.errors,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QualityScreenResult":
        obj = cls(
            config=QualityScreenConfig.from_dict(d["config"]),
            run_date=d["run_date"],
            universe_size=d["universe_size"],
            after_profitability=d["after_profitability"],
            after_balance_sheet=d["after_balance_sheet"],
            after_earnings_quality=d["after_earnings_quality"],
            run_seconds=d.get("run_seconds", 0.0),
            errors=d.get("errors", []),
        )
        obj.survivors  = [StockScreenMetrics.from_dict(s) for s in d.get("survivors", [])]
        obj.all_metrics = [StockScreenMetrics.from_dict(s) for s in d.get("all_metrics", [])]
        return obj
