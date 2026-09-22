"""
m3emz Backtester — Backtesting Engine
"""

import pandas as pd
import numpy as np


class Trade:
    def __init__(self, entry_time, entry_price, size, direction,
                 stop_loss=None, take_profit=None, tag=""):
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.size = size
        self.direction = direction
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.tag = tag
        self.exit_time = None
        self.exit_price = None
        self.exit_reason = None
        self.pnl = 0.0
        self.pnl_pct = 0.0

    def close(self, exit_time, exit_price, reason="signal"):
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = reason
        if self.direction == "long":
            self.pnl = (exit_price - self.entry_price) * self.size
        else:
            self.pnl = (self.entry_price - exit_price) * self.size
        self.pnl_pct = self.pnl / (self.entry_price * self.size) * 100
        return self.pnl


class Backtester:
    def __init__(self, df: pd.DataFrame, cash=10_000, commission=0.001, interval="1h"):
        self.df = df.copy()
        self.cash = cash
        self.init_cash = cash
        self.commission = commission
        self.interval = interval
        self.trades = []
        self.equity = []
        self._position = None

    def buy(self, i, price, size_pct=1.0, stop_loss=None, take_profit=None, tag=""):
        if self._position:
            return
        spend = self.cash * size_pct
        spend -= spend * self.commission
        size = spend / price
        self.cash -= spend + spend * self.commission
        self._position = Trade(
            entry_time=self.df.index[i],
            entry_price=price,
            size=size,
            direction="long",
            stop_loss=stop_loss,
            take_profit=take_profit,
            tag=tag,
        )

    def sell(self, i, price, size_pct=1.0, stop_loss=None, take_profit=None, tag=""):
        if self._position:
            return
        notional = self.cash * size_pct
        size = notional / price
        self._position = Trade(
            entry_time=self.df.index[i],
            entry_price=price,
            size=size,
            direction="short",
            stop_loss=stop_loss,
            take_profit=take_profit,
            tag=tag,
        )

    def close_position(self, i, price, reason="signal"):
        if not self._position:
            return
        t = self._position
        pnl = t.close(self.df.index[i], price, reason)
        proceeds = price * t.size
        if t.direction == "long":
            self.cash += proceeds - proceeds * self.commission
        else:
            self.cash += t.entry_price * t.size + pnl - proceeds * self.commission
        self.trades.append(t)
        self._position = None

    @property
    def in_position(self) -> bool:
        return self._position is not None

    @property
    def position_direction(self):
        return self._position.direction if self._position else None

    def run(self, strategy_fn):
        df = strategy_fn(self.df, mode="indicators")
        self.df = df

        for i in range(len(df)):
            row = df.iloc[i]
            price = float(row["Close"])

            if self._position:
                op = float(row["Open"])
                t = self._position
                if t.direction == "long":
                    if t.stop_loss and op <= t.stop_loss:
                        self.close_position(i, t.stop_loss, "SL"); continue
                    if t.take_profit and op >= t.take_profit:
                        self.close_position(i, t.take_profit, "TP"); continue
                    if t.stop_loss and price <= t.stop_loss:
                        self.close_position(i, t.stop_loss, "SL"); continue
                    if t.take_profit and price >= t.take_profit:
                        self.close_position(i, t.take_profit, "TP"); continue
                else:
                    if t.stop_loss and op >= t.stop_loss:
                        self.close_position(i, t.stop_loss, "SL"); continue
                    if t.take_profit and op <= t.take_profit:
                        self.close_position(i, t.take_profit, "TP"); continue
                    if t.stop_loss and price >= t.stop_loss:
                        self.close_position(i, t.stop_loss, "SL"); continue
                    if t.take_profit and price <= t.take_profit:
                        self.close_position(i, t.take_profit, "TP"); continue

            strategy_fn(df, i, self)

            mark = price
            pos_value = 0
            if self._position:
                t = self._position
                if t.direction == "long":
                    pos_value = mark * t.size
                else:
                    pos_value = t.entry_price * t.size + (t.entry_price - mark) * t.size
            self.equity.append({
                "date": df.index[i],
                "equity": self.cash + pos_value,
                "price": price,
            })

        if self._position:
            self.close_position(len(df) - 1, float(df["Close"].iloc[-1]), "EOD")

        return self

    def stats(self) -> dict:
        if not self.equity:
            return {"Total Return %": 0, "Total Trades": 0}

        eq = pd.DataFrame(self.equity).set_index("date")["equity"]
        rets = eq.pct_change().dropna()

        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        total_return = (eq.iloc[-1] - self.init_cash) / self.init_cash * 100
        bah_return = (self.df["Close"].iloc[-1] - self.df["Close"].iloc[0]) / self.df["Close"].iloc[0] * 100

        roll_max = eq.cummax()
        dd = (eq - roll_max) / roll_max * 100
        max_dd = dd.min()

        periods_per_year = {
            "1m": 525600, "3m": 175200, "5m": 105120, "15m": 35040,
            "30m": 17520, "1h": 8760, "4h": 2190, "1d": 252, "1w": 52
        }.get(self.interval, 252)
        sharpe = (rets.mean() / rets.std()) * np.sqrt(periods_per_year) if rets.std() != 0 else 0

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

        durations = []
        for t in self.trades:
            if t.exit_time and t.entry_time:
                durations.append((t.exit_time - t.entry_time).total_seconds() / 3600)

        sl_count = len([t for t in self.trades if t.exit_reason == "SL"])
        tp_count = len([t for t in self.trades if t.exit_reason == "TP"])

        commission_paid = 0
        for t in self.trades:
            entry_val = t.entry_price * t.size
            exit_val = (t.exit_price or t.entry_price) * t.size
            commission_paid += (entry_val + exit_val) * self.commission

        return {
            "Total Return %": round(total_return, 2),
            "B&H Return %": round(bah_return, 2),
            "Sharpe Ratio": round(sharpe, 3),
            "Profit Factor": round(profit_factor, 3),
            "Win Rate %": round(len(wins) / len(self.trades) * 100, 1) if self.trades else 0,
            "Max Drawdown %": round(max_dd, 2),
            "Total Trades": len(self.trades),
            "Avg Win $": round(np.mean([t.pnl for t in wins]), 2) if wins else 0,
            "Avg Loss $": round(np.mean([t.pnl for t in losses]), 2) if losses else 0,
            "Largest Win $": round(max((t.pnl for t in wins), default=0), 2),
            "Largest Loss $": round(min((t.pnl for t in losses), default=0), 2),
            "SL Exits": sl_count,
            "TP Exits": tp_count,
            "Avg Duration h": round(np.mean(durations), 1) if durations else 0,
            "Final Equity $": round(eq.iloc[-1], 2),
            "Commission Paid $": round(commission_paid, 2),
        }

    def get_equity_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.equity).set_index("date")
