import pandas as pd
import numpy as np
from core.indicators import Indicators


def strategy_rsi_vwap(df, i=None, bt=None, mode=None):
    """RSI + Rolling VWAP Trend Rider"""
    RSI_BUY = 35
    RSI_SELL = 65
    ATR_SL = 2.0
    ATR_TP = 3.0
    VWAP_WIN = 20

    if mode == "indicators":
        df["RSI"] = Indicators.rsi(df["Close"], 14)
        df["VWAP"] = Indicators.vwap(df["High"], df["Low"], df["Close"], df["Volume"], VWAP_WIN)
        df["ATR"] = Indicators.atr(df["High"], df["Low"], df["Close"], 14)
        return df

    if i < 20:
        return
    row = df.iloc[i]
    prev_row = df.iloc[i - 1]
    rsi, vwap, atr, close = row["RSI"], row["VWAP"], row["ATR"], row["Close"]

    if pd.isna(atr) or atr <= 0:
        return

    if not bt.in_position:
        vwap_cross = prev_row["Close"] < prev_row["VWAP"] and close > vwap
        if rsi < RSI_BUY and vwap_cross:
            sl = close - ATR_SL * atr
            tp = close + ATR_TP * atr
            if sl < close and tp > close:
                bt.buy(i, close, stop_loss=sl, take_profit=tp, tag="RSI+VWAP")
    elif bt.position_direction == "long":
        if rsi > RSI_SELL or close < vwap:
            bt.close_position(i, close)
