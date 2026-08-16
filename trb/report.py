"""Markdown tables and ASCII curves. No plotting dependencies on purpose."""

from __future__ import annotations

from .model import Workload
from .simulator import Result

COLUMNS = [
    ("policy", lambda r: r.policy),
    ("RTR", lambda r: f"{r.resident_token_rent:,}"),
    ("mean", lambda r: f"{r.mean_resident_tokens:,.0f}"),
    ("peak", lambda r: f"{r.peak_resident_tokens:,}"),
    ("peak #", lambda r: str(r.peak_resident_count)),
    ("searches", lambda r: str(r.searches)),
    ("reloads", lambda r: str(r.reloads)),
    ("thrash", lambda r: f"{r.thrash_rate:.0%}"),
    ("total tokens", lambda r: f"{r.total_tokens:,}"),
    ("vs search-only", lambda r: getattr(r, "_delta", "")),
    ("opt gap", lambda r: getattr(r, "_gap", "")),
]


def _annotate(results: list[Result]) -> None:
    """Two reference points per row: the shipped default, and the optimum.

    `vs search-only` says how much a policy improves on what real systems do
    today. `opt gap` says how much of the achievable win it actually captured,
    which is the more demanding of the two and the one that stays meaningful
    once every policy beats search-only.
    """
    base = next((r for r in results if r.policy == "search-only"), None)
    opt = next((r for r in results if r.policy == "rent-optimal"), None)
    for r in results:
        if base is None or base.total_tokens == 0:
            r._delta = ""
        elif r is base:
            r._delta = "baseline"
        else:
            pct = 100 * (r.total_tokens - base.total_tokens) / base.total_tokens
            r._delta = f"{pct:+.0f}%"

        if opt is None or opt.total_tokens == 0:
            r._gap = ""
        elif r is opt:
            r._gap = "1.00x"
        else:
            r._gap = f"{r.total_tokens / opt.total_tokens:.2f}x"


def table(results: list[Result]) -> str:
    _annotate(results)
    head = "| " + " | ".join(c[0] for c in COLUMNS) + " |"
    rule = "|" + "|".join("---" for _ in COLUMNS) + "|"
    rows = ["| " + " | ".join(f(r) for _, f in COLUMNS) + " |" for r in results]
    return "\n".join([head, rule, *rows])


def curve(results: list[Result], height: int = 12, width: int = 68) -> str:
    """Overlay the resident-token curves of several policies as ASCII art."""
    if not results:
        return ""
    marks = "#*o+.:~="
    top = max(max(r.series) for r in results) or 1
    n = max(len(r.series) for r in results)
    grid = [[" "] * width for _ in range(height)]

    for idx, r in enumerate(results):
        mark = marks[idx % len(marks)]
        for col in range(width):
            lo = col * n // width
            hi = max(lo + 1, (col + 1) * n // width)
            window = r.series[lo:hi]
            if not window:
                continue
            val = max(window)
            row = height - 1 - int(val / top * (height - 1))
            if grid[row][col] == " ":
                grid[row][col] = mark

    lines = []
    for i, row in enumerate(grid):
        axis = f"{int(top * (height - 1 - i) / (height - 1)):>7,} |"
        lines.append(axis + "".join(row))
    lines.append(" " * 8 + "+" + "-" * width)
    lines.append(" " * 9 + f"0{'turn':^{width - 8}}{n}")
    legend = "  ".join(
        f"{marks[i % len(marks)]} {r.policy}" for i, r in enumerate(results)
    )
    lines.append(" " * 9 + legend)
    lines.append(" " * 9 + "(curves that coincide are drawn once, in legend order)")
    return "\n".join(lines)


def workload_section(wl: Workload, results: list[Result], curve_for: list[str]) -> str:
    used = len(wl.used_tools())
    parts = [
        f"### `{wl.name}`",
        "",
        wl.description,
        "",
        f"{len(wl)} turns &middot; {used} distinct tools used &middot; "
        f"catalog of {len(wl.catalog)} tools "
        f"({wl.catalog_tokens:,} tokens if all resident)",
        "",
        table(results),
        "",
    ]
    picked = [r for r in results if r.policy in curve_for]
    if picked:
        parts += ["```text", curve(picked), "```", ""]
    return "\n".join(parts)
