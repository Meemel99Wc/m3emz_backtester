"""
m3emz Backtester — Dynamic Strategy Loader
"""

import importlib.util
import inspect
import os
import sys

import pandas as pd
import numpy as np
from core.indicators import Indicators


def load_strategy_from_file(filepath: str) -> dict:
    """
    Load a strategy .py file dynamically.
    Returns dict of {name: function} for all strategy_* functions found.
    Raises ValueError if no valid strategy function is found.
    """
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)

    # Inject dependencies into the module namespace
    module.Indicators = Indicators
    module.pd = pd
    module.np = np

    spec.loader.exec_module(module)

    # Find functions starting with "strategy_"
    strategies = {
        name: fn for name, fn in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("strategy_")
    }

    if not strategies:
        raise ValueError("No function starting with 'strategy_' found in file")

    # Validate signature: must accept (df, ...) and (mode, ...)
    for name, fn in strategies.items():
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        if "df" not in params or "mode" not in params:
            raise ValueError(
                f"Function {name} must accept 'df' and 'mode' parameters. "
                f"Found params: {params}"
            )

    return strategies


def load_all_strategies(strategies_dir: str) -> dict:
    """
    Load all strategy .py files from a directory.
    Returns dict of {display_name: function}.
    """
    all_strategies = {}

    if not os.path.isdir(strategies_dir):
        return all_strategies

    for filename in sorted(os.listdir(strategies_dir)):
        if filename.startswith("__") or not filename.endswith(".py"):
            continue
        filepath = os.path.join(strategies_dir, filename)
        try:
            strats = load_strategy_from_file(filepath)
            for func_name, func in strats.items():
                display_name = func_name.replace("strategy_", "").replace("_", " ").title().replace(" ", "_")
                all_strategies[display_name] = func
        except Exception as e:
            print(f"Warning: Could not load {filename}: {e}")

    return all_strategies


def extract_strategy_code(text: str) -> str:
    """
    Extract Python code block from Claude's response.
    Looks for ```python ... ``` blocks.
    """
    lines = text.split("\n")
    in_block = False
    code_lines = []

    for line in lines:
        if line.strip().startswith("```python"):
            in_block = True
            continue
        elif line.strip() == "```" and in_block:
            in_block = False
            continue
        elif in_block:
            code_lines.append(line)

    return "\n".join(code_lines)


def save_strategy_code(code: str, strategies_dir: str, name: str = None) -> str:
    """
    Save strategy code to a .py file in the strategies directory.
    Returns the filepath.
    """
    from datetime import datetime

    if name is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"claude_generated_{ts}"

    # Ensure the code has necessary imports
    header_lines = [
        "import pandas as pd",
        "import numpy as np",
        "from core.indicators import Indicators",
        "",
    ]

    # Check if imports already exist
    if "import pandas" not in code:
        code = "\n".join(header_lines) + "\n" + code

    filepath = os.path.join(strategies_dir, f"{name}.py")
    with open(filepath, "w") as f:
        f.write(code)

    return filepath
