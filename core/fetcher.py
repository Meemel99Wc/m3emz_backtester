"""
m3emz Backtester — Binance Data Fetcher (with incremental cache support)
"""

import requests
import pandas as pd
from datetime import datetime, timedelta


class BinanceFetcher:
    BASE = "https://api.binance.com/api/v3/klines"

    INTERVALS = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000,
        "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000,
        "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000,
    }

    @staticmethod
    def _parse_lookback(lookback: str) -> int:
        lookback = lookback.lower().strip()
        now = datetime.utcnow()
        num = int("".join(filter(str.isdigit, lookback.split()[0])))
        if "day" in lookback:
            delta = timedelta(days=num)
        elif "week" in lookback:
            delta = timedelta(weeks=num)
        elif "month" in lookback:
            delta = timedelta(days=num * 30)
        elif "hour" in lookback:
            delta = timedelta(hours=num)
        elif "year" in lookback:
            delta = timedelta(days=num * 365)
        else:
            delta = timedelta(days=num)
        return int((now - delta).timestamp() * 1000)

    @classmethod
    def fetch(cls, symbol: str, interval: str, lookback: str) -> pd.DataFrame:
        start_ms = cls._parse_lookback(lookback)
        return cls._fetch_candles(symbol, interval, start_ms)

    @classmethod
    def fetch_from_ms(cls, symbol: str, interval: str, start_ms: int) -> pd.DataFrame:
        """Fetch candles starting from a specific timestamp in ms."""
        return cls._fetch_candles(symbol, interval, start_ms)

    @classmethod
    def _fetch_candles(cls, symbol: str, interval: str, start_ms: int) -> pd.DataFrame:
        ms_per_candle = cls.INTERVALS.get(interval, 3_600_000)
        all_candles = []

        while True:
            params = {
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": start_ms,
                "limit": 1000,
            }
            try:
                resp = requests.get(cls.BASE, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                raise ConnectionError(f"Binance API error: {e}")

            if not data:
                break

            all_candles.extend(data)
            last_open = data[-1][0]

            if len(data) < 1000 or last_open >= int(datetime.utcnow().timestamp() * 1000):
                break

            start_ms = last_open + ms_per_candle

        if not all_candles:
            raise ValueError(f"No data returned for {symbol} {interval}")

        df = pd.DataFrame(all_candles, columns=[
            "Open_time", "Open", "High", "Low", "Close", "Volume",
            "Close_time", "Quote_volume", "Trades",
            "Taker_buy_base", "Taker_buy_quote", "Ignore"
        ])
        df["Open_time"] = pd.to_datetime(df["Open_time"], unit="ms")
        df.set_index("Open_time", inplace=True)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = df[col].astype(float)
        df.index.name = "Date"
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()
