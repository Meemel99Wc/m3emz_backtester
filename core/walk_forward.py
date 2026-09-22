"""
m3emz Backtester — Walk-Forward Testing Engine
Splits data into N rolling windows, trains on train_pct, tests on remainder.
"""

import pandas as pd
import numpy as np
from core.engine import Backtester


class WalkForwardTester:
    def __init__(self, df, strategy_fn, n_splits=5, train_pct=0.7,
                 cash=10_000, commission=0.001, interval="1h"):
        self.df = df.copy()
        self.strategy_fn = strategy_fn
        self.n_splits = n_splits
        self.train_pct = train_pct
        self.cash = cash
        self.commission = commission
        self.interval = interval

    def run(self) -> dict:
        n = len(self.df)
        fold_size = n // self.n_splits
        if fold_size < 50:
            raise ValueError(
                f"Not enough data for {self.n_splits} folds "
                f"({n} candles, {fold_size} per fold). Need at least 50 per fold."
            )

        folds = []
        in_returns = []
        out_returns = []

        for i in range(self.n_splits):
            start = i * fold_size
            end = start + fold_size if i < self.n_splits - 1 else n
            fold_df = self.df.iloc[start:end].copy()

            split_idx = int(len(fold_df) * self.train_pct)
            train_df = fold_df.iloc[:split_idx].copy()
            test_df = fold_df.iloc[split_idx:].copy()

            if len(train_df) < 30 or len(test_df) < 10:
                continue

            # In-sample run
            bt_train = Backtester(train_df, cash=self.cash,
                                  commission=self.commission, interval=self.interval)
            bt_train.run(self.strategy_fn)
            train_stats = bt_train.stats()

            # Out-of-sample run
            bt_test = Backtester(test_df, cash=self.cash,
                                 commission=self.commission, interval=self.interval)
            bt_test.run(self.strategy_fn)
            test_stats = bt_test.stats()

            eq_df = bt_test.get_equity_df()
            eq_series = eq_df["equity"] if not eq_df.empty else pd.Series(dtype=float)

            fold_result = {
                "fold": i + 1,
                "train_start": train_df.index[0],
                "train_end": train_df.index[-1],
                "test_start": test_df.index[0],
                "test_end": test_df.index[-1],
                "in_sample_return": train_stats.get("Total Return %", 0),
                "out_sample_return": test_stats.get("Total Return %", 0),
                "in_sample_sharpe": train_stats.get("Sharpe Ratio", 0),
                "out_sample_sharpe": test_stats.get("Sharpe Ratio", 0),
                "trades": bt_test.trades,
                "equity": eq_series,
            }
            folds.append(fold_result)
            in_returns.append(fold_result["in_sample_return"])
            out_returns.append(fold_result["out_sample_return"])

        if not folds:
            return {
                "folds": [],
                "efficiency_ratio": 0,
                "consistent_folds": 0,
                "verdict": "Insufficient Data",
            }

        avg_in = np.mean(in_returns) if in_returns else 0
        avg_out = np.mean(out_returns) if out_returns else 0
        efficiency = avg_out / avg_in if avg_in != 0 else 0
        consistent = sum(1 for r in out_returns if r > 0)

        if efficiency > 0.5 and consistent >= len(folds) * 0.6:
            verdict = "Robust"
        elif efficiency > 0.3 and consistent >= len(folds) * 0.4:
            verdict = "Marginal"
        else:
            verdict = "Overfitted"

        return {
            "folds": folds,
            "efficiency_ratio": round(efficiency, 3),
            "consistent_folds": consistent,
            "verdict": verdict,
        }
