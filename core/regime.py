"""
m3emz Backtester — Market Regime Detection Engine
Classifies each candle into one of 4 regimes based on ADX, SMA200, and ATR.
"""

import pandas as pd
import numpy as np
from core.indicators import Indicators


class RegimeDetector:
    REGIMES = {
        0: ("Trending Bull",   "#00ff88", "\u2197"),
        1: ("Trending Bear",   "#ff4444", "\u2198"),
        2: ("Ranging",         "#f59e0b", "\u2194"),
        3: ("High Volatility", "#a78bfa", "\u26a1"),
    }

    @staticmethod
    def classify(df: pd.DataFrame) -> pd.Series:
        """Return a Series of regime ints (0-3) aligned with df.index."""
        adx = Indicators.adx(df["High"], df["Low"], df["Close"], 14)
        sma200 = Indicators.sma(df["Close"], 200)
        atr = Indicators.atr(df["High"], df["Low"], df["Close"], 14)

        # ATR percentile (rolling 100-period window)
        atr_pct = atr.rolling(100, min_periods=20).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
        )

        regimes = pd.Series(2, index=df.index, dtype=int)  # default: Ranging

        trending = adx > 25
        ranging = adx < 20
        bullish = df["Close"] > sma200
        bearish = df["Close"] < sma200
        high_vol = atr_pct > 0.80

        # High volatility takes priority
        regimes[high_vol] = 3
        # Then trending
        regimes[trending & bullish & ~high_vol] = 0
        regimes[trending & bearish & ~high_vol] = 1
        # Ranging is the default for ADX < 20 and not high vol
        regimes[ranging & ~high_vol] = 2

        return regimes

    @staticmethod
    def get_regime_stats(trades: list, regimes: pd.Series) -> dict:
        """
        For each regime: count trades, win rate, avg PnL.
        Matches trade entry_time to the closest regime value.
        """
        stats = {}
        for regime_id, (name, color, icon) in RegimeDetector.REGIMES.items():
            stats[name] = {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0,
                           "color": color, "icon": icon}

        if not trades or regimes.empty:
            return stats

        regime_idx = regimes.index

        for t in trades:
            entry = t.entry_time
            if entry is None:
                continue
            # Find nearest regime index
            idx_pos = regime_idx.searchsorted(entry, side="right") - 1
            if idx_pos < 0:
                idx_pos = 0
            if idx_pos >= len(regime_idx):
                idx_pos = len(regime_idx) - 1
            regime_val = regimes.iloc[idx_pos]
            regime_name = RegimeDetector.REGIMES.get(regime_val, ("Ranging", "", ""))[0]
            if regime_name not in stats:
                continue
            stats[regime_name]["trades"] += 1
            stats[regime_name].setdefault("_pnls", []).append(t.pnl)

        for name, data in stats.items():
            pnls = data.pop("_pnls", [])
            if pnls:
                data["trades"] = len(pnls)
                data["win_rate"] = round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 1)
                data["avg_pnl"] = round(np.mean(pnls), 2)

        return stats
