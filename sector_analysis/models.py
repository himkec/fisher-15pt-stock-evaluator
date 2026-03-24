"""
Epic 1 — Data models for Sector Analysis.

All models implement to_dict() / from_dict() for SQLite cache serialisation.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisConfig:
    """Epic 6 — user-facing configuration for the full pipeline."""
    lookback_years:        int   = 3
    top_sectors_n:         int   = 5
    top_subsectors_n:      int   = 4
    min_market_cap_b:      float = 1.0   # $B — exclude micro-caps from universe
    benchmark:             str   = "SPY"

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class StockItem:
    """Epic 5 — one stock inside a subsector universe."""
    ticker:          str
    name:            str
    sub_industry:    str
    market_cap_b:    float   # market cap in $B
    total_return:    float   # fractional, over lookback period
    ytd_return:      float
    pe_ratio:        float   # 0 if N/A
    revenue_growth:  float   # 3Y CAGR, 0 if N/A

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class SubsectorResult:
    """Epic 4 — performance of one GICS sub-industry (subsector)."""
    name:               str
    rank:               int
    ticker_count:       int
    total_return:       float   # equal-weighted across member stocks
    annualized_return:  float
    volatility:         float   # annualised
    sharpe:             float
    ytd_return:         float
    stocks:             list = field(default_factory=list)   # list[StockItem]
    small_sample:       bool = False   # True when ticker_count < MIN_SUBSECTOR_STOCKS

    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items() if k != "stocks"}
        d["stocks"] = [s.to_dict() for s in self.stocks]
        return d

    @classmethod
    def from_dict(cls, d: dict):
        obj = cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d and k != "stocks"})
        obj.stocks = [StockItem.from_dict(s) for s in d.get("stocks", [])]
        return obj


@dataclass
class SectorResult:
    """Epic 3 — performance of one GICS sector (from ETF proxy)."""
    name:               str
    etf:                str
    icon:               str
    rank:               int
    total_return:       float
    annualized_return:  float
    volatility:         float
    sharpe:             float
    max_drawdown:       float
    ytd_return:         float
    vs_benchmark:       float   # annualised alpha vs SPY
    subsectors:         list = field(default_factory=list)   # list[SubsectorResult]

    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items() if k != "subsectors"}
        d["subsectors"] = [s.to_dict() for s in self.subsectors]
        return d

    @classmethod
    def from_dict(cls, d: dict):
        obj = cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d and k != "subsectors"})
        obj.subsectors = [SubsectorResult.from_dict(s) for s in d.get("subsectors", [])]
        return obj


@dataclass
class AnalysisResult:
    """Epic 6 — combined output of the full pipeline."""
    config:               AnalysisConfig
    as_of_date:           str
    lookback_start:       str
    benchmark_return:     float
    benchmark_annualized: float
    all_sectors:          list = field(default_factory=list)   # list[SectorResult], all 11 ranked
    run_seconds:          float = 0.0

    @property
    def top_sectors(self) -> list:
        return self.all_sectors[: self.config.top_sectors_n]

    def to_dict(self):
        return {
            "config":               self.config.to_dict(),
            "as_of_date":           self.as_of_date,
            "lookback_start":       self.lookback_start,
            "benchmark_return":     self.benchmark_return,
            "benchmark_annualized": self.benchmark_annualized,
            "all_sectors":          [s.to_dict() for s in self.all_sectors],
            "run_seconds":          self.run_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict):
        obj = cls(
            config=AnalysisConfig.from_dict(d["config"]),
            as_of_date=d["as_of_date"],
            lookback_start=d["lookback_start"],
            benchmark_return=d["benchmark_return"],
            benchmark_annualized=d["benchmark_annualized"],
            run_seconds=d.get("run_seconds", 0.0),
        )
        obj.all_sectors = [SectorResult.from_dict(s) for s in d.get("all_sectors", [])]
        return obj
