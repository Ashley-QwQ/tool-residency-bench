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


def pareto_front(points: list[tuple[str, int, int]]) -> set[str]:
    """Names of the non-dominated points in (reactivations, rent) space.

    A policy is dominated if another one is no worse on *both* axes and
    strictly better on at least one. What survives is the set of genuine
    operating points - the ones where buying less rent really does cost more
    reactivations. Everything else is beaten outright and no choice of
    exchange rate can rescue it.
    """
    front = set()
    for name, x, y in points:
        if not any(
            (ox <= x and oy <= y) and (ox < x or oy < y)
            for other, ox, oy in points
            if other != name
        ):
            front.add(name)
    return front


def scatter(
    points: list[tuple[str, int, int]],
    trace: list[tuple[str, int, int]] | None = None,
    height: int = 16,
    width: int = 58,
) -> str:
    """Rent (log y) against reactivations (x).

    Log y because the policies span two orders of magnitude and a linear axis
    turns every interesting point into one row at the bottom. `trace` - the
    optimum evaluated at a range of prices - is drawn as a single connected
    series rather than as separate policies, because that is what it is: one
    curve, sampled.
    """
    import math

    trace = trace or []
    allp = points + trace
    if not allp:
        return ""
    marks = "abcdefghijklmnop"
    xs = [p[1] for p in allp]
    ys = [max(p[2], 1) for p in allp]
    xmax = max(xs) or 1
    lo, hi = math.log10(min(ys)), math.log10(max(ys))
    span = (hi - lo) or 1.0

    grid = [[" "] * width for _ in range(height)]

    def place(x, y, ch):
        col = int(x / xmax * (width - 1))
        row = height - 1 - int((math.log10(max(y, 1)) - lo) / span * (height - 1))
        row = min(max(row, 0), height - 1)
        grid[row][col] = ch if grid[row][col] in (" ", ".") else "*"

    for _, x, y in trace:
        place(x, y, ".")
    legend = []
    for i, (name, x, y) in enumerate(points):
        place(x, y, marks[i % len(marks)])
        legend.append(f"{marks[i % len(marks)]}={name}")

    lines = []
    for i, row in enumerate(grid):
        val = 10 ** (lo + span * (height - 1 - i) / (height - 1))
        lines.append(f"{int(val):>11,} |" + "".join(row))
    lines.append(" " * 12 + "+" + "-" * width)
    lines.append(" " * 13 + f"0{'reactivations':^{width - 10}}{xmax}")
    lines.append("")
    lines.append("  rent, log scale.  " + "  ".join(legend[:4]))
    for i in range(4, len(legend), 4):
        lines.append("  " + " " * 17 + "  ".join(legend[i:i + 4]))
    if trace:
        lines.append("  . = the optimum at a range of reactivation prices "
                     "(this is the frontier)")
    lines.append("  * = overlapping points")
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
