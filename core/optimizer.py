"""
m3emz Backtester — Agentic AI Optimizer Loop
Claude analyses strategy weaknesses, generates variants, backtests them, synthesises results.
"""

import json
import os
import re
from dataclasses import dataclass, field

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from core.engine import Backtester


@dataclass
class OptimizerState:
    strategy_name: str = ""
    strategy_code: str = ""
    baseline_stats: dict = field(default_factory=dict)
    hypotheses: list = field(default_factory=list)
    variants: dict = field(default_factory=dict)  # name -> {code, stats, change}
    best_variant: str = ""
    summary: str = ""
    step: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cancelled: bool = False


class AIOptimizer(QObject):
    """Runs the full AI optimization loop in a background thread."""

    step_started = pyqtSignal(int, str)          # step_num, description
    variant_ready = pyqtSignal(str, str)         # name, code
    variant_result = pyqtSignal(str, dict)       # name, stats
    optimization_complete = pyqtSignal(str, str)  # best_variant, summary
    token_usage = pyqtSignal(int, int, float)    # input, output, cost_usd
    error = pyqtSignal(str)
    log = pyqtSignal(str)                        # status messages

    def __init__(self, api_key, model, strategy_name, strategy_code,
                 backtest_stats, trades, df, config):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.df = df.copy()
        self.config = config
        self.state = OptimizerState(
            strategy_name=strategy_name,
            strategy_code=strategy_code,
            baseline_stats=backtest_stats,
        )
        self._trades_summary = self._summarize_trades(trades)

    def _summarize_trades(self, trades) -> str:
        if not trades:
            return "No trades."
        wins = sum(1 for t in trades if t.pnl > 0)
        losses = len(trades) - wins
        sl_exits = sum(1 for t in trades if t.exit_reason == "SL")
        tp_exits = sum(1 for t in trades if t.exit_reason == "TP")
        return (
            f"Total: {len(trades)} trades, {wins} wins, {losses} losses. "
            f"SL exits: {sl_exits}, TP exits: {tp_exits}. "
            f"Avg win: ${sum(t.pnl for t in trades if t.pnl > 0) / max(wins, 1):.2f}, "
            f"Avg loss: ${sum(t.pnl for t in trades if t.pnl <= 0) / max(losses, 1):.2f}"
        )

    def cancel(self):
        self.state.cancelled = True

    def _call_claude(self, system: str, user_msg: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        # Track tokens
        usage = response.usage
        self.state.total_input_tokens += usage.input_tokens
        self.state.total_output_tokens += usage.output_tokens
        cost = (usage.input_tokens * 3 + usage.output_tokens * 15) / 1_000_000
        self.token_usage.emit(
            self.state.total_input_tokens,
            self.state.total_output_tokens,
            cost,
        )
        return response.content[0].text

    def run_optimization_loop(self, max_iterations=5):
        try:
            self._run(max_iterations)
        except Exception as e:
            self.error.emit(str(e))

    def _run(self, max_iterations):
        state = self.state
        if state.cancelled:
            return

        # ── Step 1: Baseline Analysis ──
        state.step = 1
        self.step_started.emit(1, "Analysing strategy weaknesses...")
        self.log.emit("Step 1: Asking Claude to analyse strategy...")

        system = (
            "You are an expert quantitative trading researcher. "
            "Analyse the strategy and return ONLY valid JSON."
        )
        user = (
            f"Strategy code:\n```python\n{state.strategy_code}\n```\n\n"
            f"Backtest stats:\n{json.dumps(state.baseline_stats, indent=2, default=str)}\n\n"
            f"Trade summary: {self._trades_summary}\n\n"
            "Return a JSON object with:\n"
            '{"weaknesses": ["..."], "hypotheses": [{"change": "...", "rationale": "..."}], '
            '"recommended_order": [0, 1, ...]}\n'
            f"Max {max_iterations} hypotheses. Be specific about parameter changes."
        )
        raw = self._call_claude(system, user)
        analysis = self._extract_json(raw)
        if not analysis or "hypotheses" not in analysis:
            self.error.emit("Claude did not return valid analysis JSON.")
            return

        state.hypotheses = analysis.get("hypotheses", [])[:max_iterations]
        order = analysis.get("recommended_order", list(range(len(state.hypotheses))))
        weaknesses = analysis.get("weaknesses", [])
        self.log.emit(f"Weaknesses found: {len(weaknesses)}")
        self.log.emit(f"Hypotheses: {len(state.hypotheses)}")

        if state.cancelled:
            return

        # ── Step 2 & 3: Generate & Test Variants ──
        state.step = 2
        self.step_started.emit(2, "Generating and testing variants...")

        for idx in order:
            if state.cancelled:
                return
            if idx >= len(state.hypotheses):
                continue

            hyp = state.hypotheses[idx]
            variant_name = f"v{idx + 1}: {hyp['change'][:40]}"
            self.log.emit(f"Generating variant {idx + 1}: {hyp['change']}")

            # Ask Claude to generate the variant
            gen_system = (
                "You are an expert Python trading strategy developer. "
                "Output ONLY the complete modified strategy function inside "
                "a ```python code block. No explanation."
            )
            gen_user = (
                f"Original strategy:\n```python\n{state.strategy_code}\n```\n\n"
                f"Modification: {hyp['change']}\n"
                f"Rationale: {hyp['rationale']}\n\n"
                "Output the COMPLETE modified function. Keep the same function name."
            )
            variant_code = self._call_claude(gen_system, gen_user)
            code = self._extract_code(variant_code)
            if not code:
                self.log.emit(f"Failed to extract code for variant {idx + 1}")
                continue

            self.variant_ready.emit(variant_name, code)

            # Run backtest
            try:
                stats = self._run_variant(code)
                state.variants[variant_name] = {
                    "code": code,
                    "stats": stats,
                    "change": hyp["change"],
                }
                self.variant_result.emit(variant_name, stats)
                self.log.emit(
                    f"  Result: Return={stats.get('Total Return %', 0)}%, "
                    f"Sharpe={stats.get('Sharpe Ratio', 0)}"
                )
            except Exception as e:
                self.log.emit(f"  Variant failed: {e}")

        if state.cancelled or not state.variants:
            if not state.variants:
                self.error.emit("No variants were successfully tested.")
            return

        # ── Step 4: Find best variant ──
        state.step = 4
        self.step_started.emit(4, "Synthesising results...")

        best_name = max(
            state.variants,
            key=lambda k: state.variants[k]["stats"].get("Sharpe Ratio", 0),
        )
        state.best_variant = best_name

        # ── Step 5: Claude Synthesis ──
        results_text = "Baseline:\n" + json.dumps(state.baseline_stats, indent=2, default=str) + "\n\n"
        for name, data in state.variants.items():
            results_text += f"{name} ({data['change']}):\n"
            results_text += json.dumps(data["stats"], indent=2, default=str) + "\n\n"

        synth_system = "You are a quant researcher. Summarise backtest results concisely."
        synth_user = (
            f"Original strategy: {state.strategy_name}\n\n"
            f"Results:\n{results_text}\n"
            "Which variant is best? Should the user adopt it? "
            "Could combining changes help? Be specific and brief (3-5 sentences)."
        )
        summary = self._call_claude(synth_system, synth_user)
        state.summary = summary

        self.optimization_complete.emit(best_name, summary)

    def _run_variant(self, code: str) -> dict:
        """Dynamically execute variant code and run a backtest."""
        namespace = {}
        # Add necessary imports to the namespace
        import pandas as pd
        import numpy as np
        from core.indicators import Indicators
        namespace["pd"] = pd
        namespace["np"] = np
        namespace["Indicators"] = Indicators

        exec(code, namespace)

        # Find the strategy function
        fn = None
        for name, obj in namespace.items():
            if callable(obj) and name.startswith("strategy_"):
                fn = obj
                break

        if fn is None:
            raise ValueError("No strategy_* function found in variant code")

        bt = Backtester(
            self.df.copy(),
            cash=self.config.get("cash", 10_000),
            commission=self.config.get("commission", 0.001),
            interval=self.config.get("interval", "1h"),
        )
        bt.run(fn)
        return bt.stats()

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from Claude response."""
        # Try to find JSON in code blocks first
        match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        # Try the whole text
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        # Try to find { ... } in text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    def _extract_code(self, text: str) -> str:
        """Extract Python code from markdown code block."""
        match = re.search(r'```python\s*\n?(.*?)```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r'```\s*\n?(.*?)```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def get_best_variant_code(self) -> str:
        if self.state.best_variant and self.state.best_variant in self.state.variants:
            return self.state.variants[self.state.best_variant]["code"]
        return ""


class OptimizerThread(QThread):
    """Wrapper thread to run AIOptimizer."""

    def __init__(self, optimizer: AIOptimizer, max_iterations=5):
        super().__init__()
        self.optimizer = optimizer
        self.max_iterations = max_iterations

    def run(self):
        self.optimizer.run_optimization_loop(self.max_iterations)
