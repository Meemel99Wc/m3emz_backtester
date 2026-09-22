import pandas as pd
import numpy as np
from core.indicators import Indicators


def strategy_bollinger_bounce(df, i=None, bt=None, mode=None):
    """Bollinger Band Mean Reversion"""
    if mode == "indicators":
        bb_u, bb_m, bb_l = Indicators.bollinger_bands(df["Close"], 20, 2)
        df["BB_Upper"] = bb_u
        df["BB_Mid"] = bb_m
        df["BB_Lower"] = bb_l
        df["RSI"] = Indicators.rsi(df["Close"], 14)
        df["ATR"] = Indicators.atr(df["High"], df["Low"], df["Close"], 14)
        return df

    if i < 22:
        return
    row = df.iloc[i]
    close = row["Close"]
    atr = row["ATR"]

    if pd.isna(atr) or atr <= 0:
        return

    if not bt.in_position:
        if close <= row["BB_Lower"] and row["RSI"] < 35:
            sl = row["BB_Lower"] - 0.5 * atr
            tp = row["BB_Upper"]
            if sl < close and tp > close:
                bt.buy(i, close, stop_loss=sl, take_profit=tp, tag="BB_Bounce")
    elif bt.position_direction == "long":
        if close >= row["BB_Mid"]:
            bt.close_position(i, close)
