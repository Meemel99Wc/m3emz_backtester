import pandas as pd
import numpy as np
from core.indicators import Indicators


def strategy_ema_crossover(df, i=None, bt=None, mode=None):
    """Classic EMA 9/21 Crossover"""
    if mode == "indicators":
        df["EMA9"] = Indicators.ema(df["Close"], 9)
        df["EMA21"] = Indicators.ema(df["Close"], 21)
        df["ATR"] = Indicators.atr(df["High"], df["Low"], df["Close"], 14)
        return df

    if i < 25:
        return
    row, prev = df.iloc[i], df.iloc[i - 1]
    close = row["Close"]
    atr = row["ATR"]

    if pd.isna(atr) or atr <= 0:
        return

    crossed_up = prev["EMA9"] < prev["EMA21"] and row["EMA9"] > row["EMA21"]
    crossed_down = prev["EMA9"] > prev["EMA21"] and row["EMA9"] < row["EMA21"]

    if not bt.in_position:
        if crossed_up:
            sl = close - 1.5 * atr
            tp = close + 2.5 * atr
            if sl < close and tp > close:
                bt.buy(i, close, stop_loss=sl, take_profit=tp, tag="EMA_X")
    elif bt.position_direction == "long" and crossed_down:
        bt.close_position(i, close)
