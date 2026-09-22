import pandas as pd
import numpy as np
from core.indicators import Indicators


def strategy_macd_momentum(df, i=None, bt=None, mode=None):
    """MACD + ADX Momentum"""
    ADX_THRESHOLD = 20

    if mode == "indicators":
        macd, signal, hist = Indicators.macd(df["Close"])
        df["MACD"] = macd
        df["MACD_Signal"] = signal
        df["MACD_Hist"] = hist
        df["ADX"] = Indicators.adx(df["High"], df["Low"], df["Close"], 14)
        df["ATR"] = Indicators.atr(df["High"], df["Low"], df["Close"], 14)
        return df

    if i < 30:
        return
    row, prev = df.iloc[i], df.iloc[i - 1]
    close = row["Close"]
    atr = row["ATR"]

    if pd.isna(atr) or atr <= 0:
        return

    hist_crossed_up = prev["MACD_Hist"] <= 0 and row["MACD_Hist"] > 0
    hist_crossed_down = prev["MACD_Hist"] >= 0 and row["MACD_Hist"] < 0

    if not bt.in_position:
        if hist_crossed_up and row["ADX"] > ADX_THRESHOLD:
            sl = close - 1.8 * atr
            tp = close + 2.8 * atr
            if sl < close and tp > close:
                bt.buy(i, close, stop_loss=sl, take_profit=tp, tag="MACD_Momentum")
    elif bt.position_direction == "long":
        if hist_crossed_down:
            bt.close_position(i, close)
