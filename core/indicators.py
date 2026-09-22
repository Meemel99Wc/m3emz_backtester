"""
m3emz Backtester — Technical Indicators
"""

import pandas as pd
import numpy as np


class Indicators:

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        return series.rolling(window=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series: pd.Series, fast=12, slow=26, signal=9):
        ema_fast = Indicators.ema(series, fast)
        ema_slow = Indicators.ema(series, slow)
        macd_line = ema_fast - ema_slow
        signal_line = Indicators.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(series: pd.Series, period=20, std_dev=2):
        mid = Indicators.sma(series, period)
        std = series.rolling(period).std()
        upper = mid + std_dev * std
        lower = mid - std_dev * std
        return upper, mid, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period=20) -> pd.Series:
        tp = (high + low + close) / 3
        tpv = tp * volume
        return tpv.rolling(period).sum() / volume.rolling(period).sum()

    @staticmethod
    def adx(high, low, close, period=14):
        tr = Indicators.atr(high, low, close, 1)
        up = high.diff()
        dn = -low.diff()
        pos_dm = np.where((up > dn) & (up > 0), up, 0.0)
        neg_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
        pos_dm = pd.Series(pos_dm, index=high.index).rolling(period).mean()
        neg_dm = pd.Series(neg_dm, index=high.index).rolling(period).mean()
        atr_ = tr.rolling(period).mean()
        pdi = 100 * pos_dm / atr_.replace(0, np.nan)
        ndi = 100 * neg_dm / atr_.replace(0, np.nan)
        dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
        return dx.rolling(period).mean()

    @staticmethod
    def stoch_rsi(series: pd.Series, rsi_period=14, stoch_period=14, k=3, d=3):
        rsi = Indicators.rsi(series, rsi_period)
        rsi_lo = rsi.rolling(stoch_period).min()
        rsi_hi = rsi.rolling(stoch_period).max()
        k_line = 100 * (rsi - rsi_lo) / (rsi_hi - rsi_lo).replace(0, np.nan)
        d_line = k_line.rolling(d).mean()
        return k_line.rolling(k).mean(), d_line
