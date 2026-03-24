"""Data models for Intrinsic Value / Valuation Models module."""

from dataclasses import dataclass, field
from typing import Any


# ── Per-method scenario ───────────────────────────────────────────────────────

@dataclass
class IVScenario:
    name: str           # "Bear" | "Base" | "Bull"
    value: float        # intrinsic value per share
    growth: float       # primary growth assumption used (FCF growth, dividend growth, etc.)
    upside_pct: float   # (value - price) / price

    def to_dict(self):
        return {"name": self.name, "value": self.value,
                "growth": self.growth, "upside_pct": self.upside_pct}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# ── DCF (Free Cash Flow) ──────────────────────────────────────────────────────

@dataclass
class DCFFCFResult:
    """Free Cash Flow DCF with Bear / Base / Bull scenarios."""
    base_fcf: float             # FCF₀ used (3-yr average)
    wacc: float
    terminal_growth: float
    forecast_years: int
    scenarios: list = field(default_factory=list)   # list[IVScenario]
    notes: list = field(default_factory=list)

    def to_dict(self):
        return {
            "base_fcf": self.base_fcf, "wacc": self.wacc,
            "terminal_growth": self.terminal_growth,
            "forecast_years": self.forecast_years,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        obj = cls(
            base_fcf=d["base_fcf"], wacc=d["wacc"],
            terminal_growth=d["terminal_growth"],
            forecast_years=d["forecast_years"],
            notes=d.get("notes", []),
        )
        obj.scenarios = [IVScenario.from_dict(s) for s in d.get("scenarios", [])]
        return obj


# ── DDM Gordon Growth ─────────────────────────────────────────────────────────

@dataclass
class DDMGordonResult:
    d1: float                   # next-year dividend per share
    required_return: float
    perpetual_growth: float
    fair_value: float           # D1 / (r - g)
    current_price: float
    upside_pct: float
    current_yield: float
    payout_ratio_eps: float
    payout_ratio_fcf: float
    yield_plus_growth: float    # heuristic expected return
    valid: bool = True          # False if r <= g
    notes: list = field(default_factory=list)

    def to_dict(self):
        return {
            "d1": self.d1, "required_return": self.required_return,
            "perpetual_growth": self.perpetual_growth, "fair_value": self.fair_value,
            "current_price": self.current_price, "upside_pct": self.upside_pct,
            "current_yield": self.current_yield, "payout_ratio_eps": self.payout_ratio_eps,
            "payout_ratio_fcf": self.payout_ratio_fcf,
            "yield_plus_growth": self.yield_plus_growth, "valid": self.valid,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


# ── DDM Multi-Period ──────────────────────────────────────────────────────────

@dataclass
class DDMMultiPeriodResult:
    forecast_dividends: list    # list of (year, dividend_per_share)
    terminal_value_pv: float
    pv_dividends: float
    fair_value: float
    current_price: float
    upside_pct: float
    required_return: float
    terminal_growth: float
    notes: list = field(default_factory=list)

    def to_dict(self):
        return {
            "forecast_dividends": self.forecast_dividends,
            "terminal_value_pv": self.terminal_value_pv,
            "pv_dividends": self.pv_dividends,
            "fair_value": self.fair_value,
            "current_price": self.current_price,
            "upside_pct": self.upside_pct,
            "required_return": self.required_return,
            "terminal_growth": self.terminal_growth,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


# ── Residual Income Model ─────────────────────────────────────────────────────

@dataclass
class RIMResult:
    book_value_per_share: float
    cost_of_equity: float
    pv_residual_incomes: float
    terminal_ri_pv: float
    fair_value: float           # bvps + pv_ri + terminal
    current_price: float
    upside_pct: float
    forecast_years: int
    notes: list = field(default_factory=list)

    def to_dict(self):
        return {
            "book_value_per_share": self.book_value_per_share,
            "cost_of_equity": self.cost_of_equity,
            "pv_residual_incomes": self.pv_residual_incomes,
            "terminal_ri_pv": self.terminal_ri_pv,
            "fair_value": self.fair_value,
            "current_price": self.current_price,
            "upside_pct": self.upside_pct,
            "forecast_years": self.forecast_years,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


# ── Graham Number ─────────────────────────────────────────────────────────────

@dataclass
class GrahamResult:
    eps: float
    bvps: float
    graham_number: float        # sqrt(22.5 × EPS × BVPS)
    current_price: float
    price_to_graham: float      # price / graham_number
    label: str                  # "Below ceiling" | "At ceiling" | "Above ceiling"
    upside_pct: float
    checks: dict = field(default_factory=dict)   # optional defensive criteria
    notes: list = field(default_factory=list)

    def to_dict(self):
        return {
            "eps": self.eps, "bvps": self.bvps,
            "graham_number": self.graham_number,
            "current_price": self.current_price,
            "price_to_graham": self.price_to_graham,
            "label": self.label, "upside_pct": self.upside_pct,
            "checks": self.checks, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


# ── Football field entry ──────────────────────────────────────────────────────

@dataclass
class FootballFieldEntry:
    method: str         # display name
    low: float          # low end (Bear or single value * 0.9)
    mid: float          # central estimate
    high: float         # high end (Bull or single value * 1.1)

    def to_dict(self):
        return {"method": self.method, "low": self.low, "mid": self.mid, "high": self.high}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# ── Combined result ───────────────────────────────────────────────────────────

@dataclass
class IntrinsicValueResult:
    ticker: str
    company_name: str
    current_price: float

    dcf_fcf: Any = None             # DCFFCFResult | None
    ddm_gordon: Any = None          # DDMGordonResult | None
    ddm_multi: Any = None           # DDMMultiPeriodResult | None
    rim: Any = None                 # RIMResult | None
    graham: Any = None              # GrahamResult | None

    football_field: list = field(default_factory=list)   # list[FootballFieldEntry]
    skipped: list = field(default_factory=list)          # methods that were not run / had no data

    def to_dict(self):
        return {
            "ticker": self.ticker, "company_name": self.company_name,
            "current_price": self.current_price,
            "dcf_fcf":    self.dcf_fcf.to_dict()    if self.dcf_fcf    else None,
            "ddm_gordon": self.ddm_gordon.to_dict()  if self.ddm_gordon else None,
            "ddm_multi":  self.ddm_multi.to_dict()   if self.ddm_multi  else None,
            "rim":        self.rim.to_dict()          if self.rim        else None,
            "graham":     self.graham.to_dict()       if self.graham     else None,
            "football_field": [f.to_dict() for f in self.football_field],
            "skipped": self.skipped,
        }

    @classmethod
    def from_dict(cls, d):
        obj = cls(
            ticker=d["ticker"], company_name=d["company_name"],
            current_price=d["current_price"],
            skipped=d.get("skipped", []),
        )
        if d.get("dcf_fcf"):
            obj.dcf_fcf = DCFFCFResult.from_dict(d["dcf_fcf"])
        if d.get("ddm_gordon"):
            obj.ddm_gordon = DDMGordonResult.from_dict(d["ddm_gordon"])
        if d.get("ddm_multi"):
            obj.ddm_multi = DDMMultiPeriodResult.from_dict(d["ddm_multi"])
        if d.get("rim"):
            obj.rim = RIMResult.from_dict(d["rim"])
        if d.get("graham"):
            obj.graham = GrahamResult.from_dict(d["graham"])
        obj.football_field = [FootballFieldEntry.from_dict(f) for f in d.get("football_field", [])]
        return obj
