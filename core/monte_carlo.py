"""
m3emz Backtester — Monte Carlo Simulation Engine
Shuffles trade PnL order to test robustness against lucky sequencing.
"""

import numpy as np


class MonteCarloSimulator:
    def __init__(self, trades: list, init_cash: float, n_simulations: int = 2000):
        self.pnls = np.array([t.pnl for t in trades], dtype=float)
        self.init_cash = init_cash
        self.n_simulations = n_simulations

    def run(self) -> dict:
        if len(self.pnls) < 3:
            return {
                "final_equities": np.array([self.init_cash]),
                "max_drawdowns": np.array([0.0]),
                "sharpe_ratios": np.array([0.0]),
                "equity_curves": [],
                "percentiles": {
                    "equity_5th": self.init_cash,
                    "equity_50th": self.init_cash,
                    "equity_95th": self.init_cash,
                    "dd_95th": 0.0,
                },
                "probability_of_profit": 0.0,
                "var_95": 0.0,
                "expected_shortfall": 0.0,
                "verdict": "Insufficient Trades",
            }

        n_trades = len(self.pnls)
        rng = np.random.default_rng(42)

        final_equities = np.zeros(self.n_simulations)
        max_drawdowns = np.zeros(self.n_simulations)
        sharpe_ratios = np.zeros(self.n_simulations)
        # Store a subset of equity curves for the fan chart
        equity_curves = []

        for sim in range(self.n_simulations):
            shuffled = rng.permutation(self.pnls)
            equity = np.empty(n_trades + 1)
            equity[0] = self.init_cash
            for j in range(n_trades):
                equity[j + 1] = equity[j] + shuffled[j]

            final_equities[sim] = equity[-1]

            # Max drawdown
            running_max = np.maximum.accumulate(equity)
            dd = (equity - running_max) / np.where(running_max != 0, running_max, 1)
            max_drawdowns[sim] = dd.min() * 100

            # Sharpe on trade-level returns
            returns = shuffled / np.where(equity[:-1] != 0, equity[:-1], 1)
            if returns.std() != 0:
                sharpe_ratios[sim] = (returns.mean() / returns.std()) * np.sqrt(252)
            else:
                sharpe_ratios[sim] = 0.0

            # Store first 200 curves for fan chart
            if sim < 200:
                equity_curves.append(equity.copy())

        # Percentiles
        eq_5 = float(np.percentile(final_equities, 5))
        eq_50 = float(np.percentile(final_equities, 50))
        eq_95 = float(np.percentile(final_equities, 95))
        dd_95 = float(np.percentile(max_drawdowns, 5))  # worst 5% drawdowns

        prob_profit = float(np.mean(final_equities > self.init_cash))

        # VaR 95 — 5th percentile of PnL
        pnl_dist = final_equities - self.init_cash
        var_95 = float(np.percentile(pnl_dist, 5))

        # Expected Shortfall — average of worst 5%
        worst_5pct = pnl_dist[pnl_dist <= np.percentile(pnl_dist, 5)]
        es = float(worst_5pct.mean()) if len(worst_5pct) > 0 else var_95

        # Verdict
        if prob_profit > 0.7 and var_95 > -self.init_cash * 0.2:
            verdict = "Statistically Robust"
        elif prob_profit > 0.5:
            verdict = "Lucky"
        else:
            verdict = "Unreliable"

        return {
            "final_equities": final_equities,
            "max_drawdowns": max_drawdowns,
            "sharpe_ratios": sharpe_ratios,
            "equity_curves": equity_curves,
            "percentiles": {
                "equity_5th": round(eq_5, 2),
                "equity_50th": round(eq_50, 2),
                "equity_95th": round(eq_95, 2),
                "dd_95th": round(dd_95, 2),
            },
            "probability_of_profit": round(prob_profit, 4),
            "var_95": round(var_95, 2),
            "expected_shortfall": round(es, 2),
            "verdict": verdict,
        }
