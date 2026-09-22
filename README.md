# 🔥 m3emz Backtester v2.0

A professional-grade crypto backtesting desktop application with Claude AI integration.

## Features

- **Dark Trading Terminal UI** — three-column layout with live charts, stats, and AI chat
- **5 Built-in Strategies** — RSI+VWAP, EMA Crossover, Bollinger Bounce, MACD Momentum, StochRSI Reversal
- **Multi-Symbol Mode** — backtest across BTC, ETH, SOL and 7 more coins simultaneously
- **Interactive Charts** — price chart with trade markers, equity curve, drawdown, indicator overlays
- **16 Performance Metrics** — Sharpe, profit factor, win rate, max drawdown, and more
- **Claude AI Assistant** — analyse results, generate strategies, diagnose and fix errors
- **Error-Fix Mode** — paste backtest errors into Claude and get fixed strategy code automatically

## Quick Start

```bash
# Unzip and enter the project
cd m3emz_backtester

# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py
```

## First-Time Setup

1. Launch the app with `python main.py`
2. Click **🔑 API Key** in the chat panel and enter your Anthropic API key
3. Configure symbol (e.g. `BTCUSDT`), interval (`1h`), and lookback (`180 days ago`)
4. Check one or more strategies in the sidebar
5. Click **▶ Run Selected**

## Multi-Symbol Mode

1. Check **Multi-Symbol Mode** in the config panel
2. Select symbols from the watchlist (BTC, ETH, SOL checked by default)
3. Add custom symbols with the **+ Add** button
4. Click **▶ Run Selected** — all checked strategies run on all checked symbols
5. A comparison table pops up when done, highlighting the best performer

## Error-Fix Mode

When a backtest produces errors (e.g. invalid SL/TP ordering):

1. Click **📋 Paste Errors** in the chat panel
2. Paste the raw error output
3. Click **Attach to Next Message** — Claude receives a structured diagnostic prompt
4. Claude explains the error and provides fixed strategy code
5. Click **⬇ Import Fixed Strategy** to overwrite the broken strategy file

## Writing Custom Strategies

```python
import pandas as pd
import numpy as np
from core.indicators import Indicators

def strategy_my_custom(df, i=None, bt=None, mode=None):
    """One-line description of strategy"""
    if mode == "indicators":
        df["RSI"] = Indicators.rsi(df["Close"], 14)
        df["ATR"] = Indicators.atr(df["High"], df["Low"], df["Close"], 14)
        return df

    if i < 20:
        return  # warmup guard

    row = df.iloc[i]
    close = row["Close"]
    atr = row["ATR"]

    if pd.isna(atr) or atr <= 0:
        return  # safety guard

    if not bt.in_position:
        if row["RSI"] < 30:
            sl = close - 2 * atr
            tp = close + 3 * atr
            if sl < close and tp > close:
                bt.buy(i, close, stop_loss=sl, take_profit=tp, tag="Custom")
    elif bt.position_direction == "long":
        if row["RSI"] > 70:
            bt.close_position(i, close)
```

Save as `strategies/my_custom.py` and it will auto-load on next launch, or import via the **📂 Import Strategy .py** button.

## Available Indicators

| Indicator | Usage |
|-----------|-------|
| RSI | `Indicators.rsi(series, period)` |
| EMA | `Indicators.ema(series, period)` |
| SMA | `Indicators.sma(series, period)` |
| MACD | `Indicators.macd(series, fast, slow, signal)` → (macd, signal, hist) |
| Bollinger Bands | `Indicators.bollinger_bands(series, period, std)` → (upper, mid, lower) |
| ATR | `Indicators.atr(high, low, close, period)` |
| VWAP | `Indicators.vwap(high, low, close, volume, period)` |
| ADX | `Indicators.adx(high, low, close, period)` |
| Stochastic RSI | `Indicators.stoch_rsi(series)` → (k, d) |

## Project Structure

```
m3emz_backtester/
├── main.py                  # Entry point
├── requirements.txt
├── README.md
├── core/
│   ├── engine.py            # Backtester engine (Trade, Backtester classes)
│   ├── fetcher.py           # Binance OHLCV data fetcher
│   ├── indicators.py        # Technical indicator library
│   └── strategy_loader.py   # Dynamic strategy import/export
├── strategies/
│   ├── rsi_vwap.py          # RSI + VWAP Trend Rider
│   ├── ema_crossover.py     # EMA 9/21 Crossover
│   ├── bollinger_bounce.py  # Bollinger Band Mean Reversion
│   ├── macd_momentum.py     # MACD + ADX Momentum
│   └── stoch_rsi.py         # Stochastic RSI Reversal
├── ui/
│   ├── main_window.py       # Main window coordinator
│   ├── config_panel.py      # Left sidebar — config + watchlist
│   ├── chart_panel.py       # Center — Matplotlib charts
│   ├── stats_panel.py       # Center bottom — stat cards
│   └── chat_panel.py        # Right — Claude AI chat + error-fix
└── utils/
    ├── theme.py             # Dark terminal colour palette + stylesheet
    └── helpers.py           # Thread workers, toast notifications, settings
```

## Settings

Settings are persisted to `~/.m3emz/config.json` including API key, last configuration, window geometry, and panel sizes.

## Requirements

- Python 3.9+
- PyQt5 >= 5.15
- matplotlib >= 3.7
- pandas >= 2.0
- numpy >= 1.24
- requests >= 2.28
- anthropic >= 0.25 (for Claude AI features)