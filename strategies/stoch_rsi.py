import pandas as pd
import numpy as np
from core.indicators import Indicators


def strategy_stoch_rsi_reversal(df, i=None, bt=None, mode=None):
    """Stochastic RSI Reversal"""
    if mode == "indicators":
        k, d = Indicators.stoch_rsi(df["Close"])
        df["SRSI_K"] = k
        df["SRSI_D"] = d
        df["ATR"] = Indicators.atr(df["High"], df["Low"], df["Close"], 14)
        return df

    if i < 32:
        return
    row, prev = df.iloc[i], df.iloc[i - 1]
    close = row["Close"]
    atr = row["ATR"]

    if pd.isna(atr) or atr <= 0:
        return

    k_crossed_up = prev["SRSI_K"] < prev["SRSI_D"] and row["SRSI_K"] > row["SRSI_D"]

    if not bt.in_position:
        if k_crossed_up and row["SRSI_K"] < 20 and row["SRSI_D"] < 20:
            sl = close - 1.5 * atr
            tp = close + 2.5 * atr
            if sl < close and tp > close:
                bt.buy(i, close, stop_loss=sl, take_profit=tp, tag="StochRSI")
    elif bt.position_direction == "long":
        if row["SRSI_K"] > 80:
            bt.close_position(i, close)
