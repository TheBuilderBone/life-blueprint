#!/usr/bin/env python3
"""
Utility Flex Funding Analyzer
Run:    python analyze.py
Add:    python analyze.py add Water 2026-07 15.00
Exclude: python analyze.py exclude Water 2026-04   (toggle exclude flag)
"""

import sys
import os
import csv
import math
import datetime

BILLS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bills.csv")
CHARTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts")
UTILITIES = ["Water", "Power", "Internet", "Trash"]

# Conservative cushion multiplier on std dev (higher = more conservative)
CUSHION_STDDEV = 1.0  # avg + 1.0 * std ≈ 84th percentile

# ─── CSV helpers ──────────────────────────────────────────────────────────────

def load_bills():
    rows = []
    with open(BILLS_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["amount"] = float(row["amount"])
            row["exclude"] = row["exclude"].strip().lower() in ("1", "true", "yes", "x")
            rows.append(row)
    return rows


def save_bills(rows):
    fieldnames = ["utility", "date", "amount", "exclude", "notes"]
    with open(BILLS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {k: row.get(k, "") for k in fieldnames}
            out["exclude"] = "true" if row["exclude"] else ""
            writer.writerow(out)


def add_bill(utility, date_str, amount_str, notes=""):
    utility = utility.capitalize()
    if utility not in UTILITIES:
        print(f"Unknown utility '{utility}'. Choose from: {', '.join(UTILITIES)}")
        sys.exit(1)
    try:
        amount = float(amount_str)
    except ValueError:
        print(f"Invalid amount '{amount_str}'")
        sys.exit(1)
    # Validate date
    try:
        datetime.datetime.strptime(date_str, "%Y-%m")
    except ValueError:
        print(f"Invalid date '{date_str}'. Use YYYY-MM format (e.g. 2026-07)")
        sys.exit(1)

    rows = load_bills()
    # Check for duplicate
    for r in rows:
        if r["utility"] == utility and r["date"] == date_str:
            print(f"Bill already exists: {utility} {date_str} = ${r['amount']:.2f}")
            print("Update the CSV directly if you need to correct it.")
            sys.exit(1)

    rows.append({"utility": utility, "date": date_str, "amount": amount,
                 "exclude": False, "notes": notes})
    rows.sort(key=lambda r: (r["date"], r["utility"]))
    save_bills(rows)
    print(f"Added: {utility} {date_str} ${amount:.2f}")


def toggle_exclude(utility, date_str):
    utility = utility.capitalize()
    rows = load_bills()
    found = False
    for r in rows:
        if r["utility"] == utility and r["date"] == date_str:
            r["exclude"] = not r["exclude"]
            state = "EXCLUDED" if r["exclude"] else "INCLUDED"
            print(f"{utility} {date_str}: now {state}")
            found = True
    if not found:
        print(f"No bill found for {utility} {date_str}")
        sys.exit(1)
    save_bills(rows)


# ─── Statistics ───────────────────────────────────────────────────────────────

def stats(values):
    n = len(values)
    if n == 0:
        return {}
    avg = sum(values) / n
    sorted_v = sorted(values)
    median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    variance = sum((x - avg) ** 2 for x in values) / max(n - 1, 1)
    std = math.sqrt(variance)

    def percentile(p):
        idx = (n - 1) * p / 100
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (idx - lo)

    return {
        "n": n, "avg": avg, "median": median, "std": std,
        "min": sorted_v[0], "max": sorted_v[-1],
        "p75": percentile(75), "p80": percentile(80),
    }


def detect_outliers(rows, utility):
    """IQR-based outlier detection for a single utility (on non-excluded rows)."""
    values = sorted(r["amount"] for r in rows
                    if r["utility"] == utility and not r["exclude"] and r["amount"] > 0)
    if len(values) < 4:
        return set()
    n = len(values)
    q1 = values[n // 4]
    q3 = values[(3 * n) // 4]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return {(r["utility"], r["date"]) for r in rows
            if r["utility"] == utility and not r["exclude"]
            and (r["amount"] < lo or r["amount"] > hi)}


def rolling_avg(values_by_date, n=12):
    """Mean of the most recent n months."""
    recent = sorted(values_by_date.items())[-n:]
    vals = [v for _, v in recent]
    return sum(vals) / len(vals) if vals else 0


def seasonal_pattern(values_by_date):
    """Returns a description of high/low months based on available data."""
    by_month = {}
    for date_str, amount in values_by_date.items():
        month = int(date_str.split("-")[1])
        by_month.setdefault(month, []).append(amount)
    avg_by_month = {m: sum(v) / len(v) for m, v in by_month.items()}
    if not avg_by_month:
        return "N/A", "N/A"
    overall_avg = sum(avg_by_month.values()) / len(avg_by_month)
    high_months = sorted([m for m, a in avg_by_month.items() if a > overall_avg * 1.1],
                         key=lambda m: -avg_by_month[m])
    low_months = sorted([m for m, a in avg_by_month.items() if a < overall_avg * 0.9],
                        key=lambda m: avg_by_month[m])
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    high_str = ", ".join(month_names[m] for m in high_months[:4]) or "none"
    low_str = ", ".join(month_names[m] for m in low_months[:4]) or "none"
    return high_str, low_str


# ─── Charts ───────────────────────────────────────────────────────────────────

PALETTE = {
    "blue":    "#2563eb",
    "amber":   "#d97706",
    "red":     "#dc2626",
    "green":   "#16a34a",
    "gray":    "#94a3b8",
    "bg":      "#f8fafc",
    "grid":    "#e2e8f0",
    "text":    "#0f172a",
    "subtext": "#64748b",
}

UTILITY_COLOR = {
    "Water":    "#0ea5e9",
    "Power":    "#f59e0b",
    "Internet": "#8b5cf6",
    "Trash":    "#10b981",
}


def _setup_ax(ax):
    ax.set_facecolor(PALETTE["bg"])
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(PALETTE["grid"])
    ax.spines["bottom"].set_color(PALETTE["grid"])
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", colors=PALETTE["subtext"], length=4)
    ax.tick_params(axis="y", colors=PALETTE["subtext"], length=0)


def generate_chart(utility, active_rows, excluded_rows, recommended, avg_val, s=None):
    """Save a polished line chart PNG for this utility."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib.lines as mlines
        import matplotlib.ticker as mticker
        import datetime
    except ImportError:
        print("  [charts skipped — install matplotlib: pip install matplotlib]")
        return

    os.makedirs(CHARTS_DIR, exist_ok=True)

    def to_date(d):
        return datetime.datetime.strptime(d, "%Y-%m")

    dates   = [to_date(r["date"]) for r in active_rows]
    amounts = [r["amount"] for r in active_rows]
    line_color = UTILITY_COLOR.get(utility, PALETTE["blue"])

    fig, ax = plt.subplots(figsize=(13, 5.5))
    fig.patch.set_facecolor("white")
    _setup_ax(ax)

    # Soft fill under the line
    ax.fill_between(dates, amounts, alpha=0.13, color=line_color, zorder=1)

    # Avg–target shaded band
    if recommended > avg_val:
        ax.axhspan(avg_val, recommended, alpha=0.06, color=PALETTE["red"], zorder=1)

    # Avg and target reference lines
    ax.axhline(avg_val,     color=PALETTE["amber"], linestyle="--", linewidth=1.5,
               alpha=0.85, zorder=2)
    ax.axhline(recommended, color=PALETTE["red"],   linestyle="--", linewidth=2.0,
               alpha=0.9,  zorder=2)

    # Main line
    ax.plot(dates, amounts, "-", linewidth=2.5, color=line_color, zorder=3)

    # Color-coded points: green below avg, red above target, line_color otherwise
    for d, a in zip(dates, amounts):
        c = (PALETTE["red"]   if a > recommended else
             PALETTE["green"] if a < avg_val     else line_color)
        ax.scatter([d], [a], s=72, color=c, zorder=5,
                   edgecolors="white", linewidths=1.8)

    # Excluded points
    if excluded_rows:
        ex_d = [to_date(r["date"])  for r in excluded_rows]
        ex_a = [r["amount"]          for r in excluded_rows]
        ax.scatter(ex_d, ex_a, s=70, color=PALETTE["gray"], marker="x",
                   linewidths=2.2, zorder=5)

    # Annotate peak and low
    if amounts:
        hi_i = amounts.index(max(amounts))
        lo_i = amounts.index(min(amounts))
        spread = max(amounts) - min(amounts) if len(amounts) > 1 else 1
        ax.annotate(f"${amounts[hi_i]:.0f}",
                    (dates[hi_i], amounts[hi_i]),
                    xytext=(0, 11), textcoords="offset points",
                    ha="center", fontsize=9, fontweight="bold",
                    color=PALETTE["red"])
        ax.annotate(f"${amounts[lo_i]:.0f}",
                    (dates[lo_i], amounts[lo_i]),
                    xytext=(0, -17), textcoords="offset points",
                    ha="center", fontsize=9, fontweight="bold",
                    color=PALETTE["green"])

    # Inline labels at the right edge of the reference lines
    if dates:
        xmax = max(dates)
        ax.text(xmax, avg_val,     f"  avg ${avg_val:.0f}",
                va="center", ha="left", fontsize=9,
                color=PALETTE["amber"], fontweight="semibold")
        ax.text(xmax, recommended, f"  fund ${recommended}",
                va="center", ha="left", fontsize=9,
                color=PALETTE["red"], fontweight="bold")

    # Axes formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45, ha="right", fontsize=9, color=PALETTE["subtext"])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.0f}"))
    ax.tick_params(axis="y", labelsize=9, labelcolor=PALETTE["subtext"])

    # Y limits with breathing room
    y_pad = (max(amounts) - min(amounts)) * 0.2 if len(amounts) > 1 else 10
    ax.set_ylim(max(0, min(amounts) - y_pad), max(amounts) + y_pad * 2.5)

    # Extend x-axis slightly right for inline labels
    if len(dates) > 1:
        span = (max(dates) - min(dates)).days
        ax.set_xlim(right=max(dates) + datetime.timedelta(days=span * 0.07))

    # Title block
    ax.set_title(utility, fontsize=19, fontweight="bold",
                 color=PALETTE["text"], pad=14, loc="left")
    n_pts = len(amounts)
    peak  = max(amounts) if amounts else 0
    fig.text(0.115, 0.91,
             f"{n_pts} months of data  •  avg ${avg_val:.0f}  •  "
             f"peak ${peak:.0f}  •  fund ${recommended}/mo",
             fontsize=9, color=PALETTE["subtext"])

    # Legend
    legend_handles = [
        mlines.Line2D([0], [0], color=PALETTE["amber"], linestyle="--",
                      linewidth=1.5, label=f"Average"),
        mlines.Line2D([0], [0], color=PALETTE["red"],   linestyle="--",
                      linewidth=2.0, label=f"Funding target"),
        plt.scatter([], [], marker="o", c=PALETTE["green"],  s=55, label="Below avg"),
        plt.scatter([], [], marker="o", c=line_color,          s=55, label="Normal"),
        plt.scatter([], [], marker="o", c=PALETTE["red"],    s=55, label="Above target"),
    ]
    if excluded_rows:
        legend_handles.append(
            mlines.Line2D([0], [0], marker="x", color=PALETTE["gray"],
                          linestyle="None", markersize=8, label="Excluded")
        )
    ax.legend(handles=legend_handles, loc="upper left",
              framealpha=0.92, edgecolor=PALETTE["grid"],
              fontsize=8.5, labelcolor=PALETTE["text"])

    ax.set_xlabel("")
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out_path = os.path.join(CHARTS_DIR, f"{utility.lower()}.png")
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"  Chart saved: charts/{utility.lower()}.png")


def generate_overview_chart(all_results):
    """Save a 2×2 summary overview of all four utilities."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib.ticker as mticker
        import datetime
    except ImportError:
        return

    os.makedirs(CHARTS_DIR, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    fig.patch.set_facecolor("white")
    fig.suptitle("Utility Flex Funding — Overview",
                 fontsize=16, fontweight="bold", color=PALETTE["text"], y=0.98)

    for ax, utility in zip(axes.flat, UTILITIES):
        if utility not in all_results:
            ax.set_visible(False)
            continue

        r = all_results[utility]
        active = r["active"]
        line_color = UTILITY_COLOR.get(utility, PALETTE["blue"])

        def to_date(d):
            return datetime.datetime.strptime(d, "%Y-%m")

        dates   = [to_date(row["date"]) for row in active if row["amount"] > 0]
        amounts = [row["amount"]         for row in active if row["amount"] > 0]

        _setup_ax(ax)
        ax.fill_between(dates, amounts, alpha=0.15, color=line_color)
        ax.plot(dates, amounts, "-", linewidth=2, color=line_color)
        for d, a in zip(dates, amounts):
            c = (PALETTE["red"]   if a > r["recommended"] else
                 PALETTE["green"] if a < r["avg"]          else line_color)
            ax.scatter([d], [a], s=45, color=c, zorder=4,
                       edgecolors="white", linewidths=1.4)
        ax.axhline(r["avg"],         color=PALETTE["amber"], linestyle="--",
                   linewidth=1.3, alpha=0.8)
        ax.axhline(r["recommended"], color=PALETTE["red"],   linestyle="--",
                   linewidth=1.7, alpha=0.9)

        ax.set_title(utility, fontsize=13, fontweight="bold",
                     color=PALETTE["text"], loc="left", pad=8)
        ax.set_title(f"fund ${r['recommended']}/mo",
                     fontsize=10, color=PALETTE["red"], loc="right", pad=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right",
                 fontsize=8, color=PALETTE["subtext"])
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.0f}"))
        ax.tick_params(axis="y", labelsize=8, labelcolor=PALETTE["subtext"])
        if amounts:
            y_pad = (max(amounts) - min(amounts)) * 0.25 if len(amounts) > 1 else 5
            ax.set_ylim(max(0, min(amounts) - y_pad), max(amounts) + y_pad * 2)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = os.path.join(CHARTS_DIR, "overview.png")
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"  Chart saved: charts/overview.png")


# ─── Main analysis ────────────────────────────────────────────────────────────

def analyze():
    rows = load_bills()

    # ── Print data sample ──────────────────────────────────────────
    print("\n" + "=" * 62)
    print("  LOADED DATA SAMPLE (first 8 rows)")
    print("=" * 62)
    print(f"  {'Utility':<10} {'Date':<10} {'Amount':>8}  {'Excl':>5}  Notes")
    print("  " + "-" * 58)
    for r in rows[:8]:
        excl = "yes" if r["exclude"] else ""
        print(f"  {r['utility']:<10} {r['date']:<10} ${r['amount']:>7.2f}  {excl:>5}  {r.get('notes','')[:30]}")
    print(f"  ... ({len(rows)} total rows across all utilities)\n")

    # ── Detect outliers ────────────────────────────────────────────
    auto_outliers = set()
    for u in UTILITIES:
        auto_outliers |= detect_outliers(rows, u)

    flagged = [(r["utility"], r["date"], r["amount"])
               for r in rows
               if (r["utility"], r["date"]) in auto_outliers and not r["exclude"]]

    if flagged:
        print("=" * 62)
        print("  AUTO-DETECTED OUTLIERS (statistically unusual)")
        print("=" * 62)
        print("  These bills are significantly above/below normal for")
        print("  their utility. To exclude one from averages, run:")
        print("    python analyze.py exclude <Utility> <YYYY-MM>")
        print()
        for u, d, a in flagged:
            print(f"    {u:<10} {d}  ${a:.2f}")
        print()

    # ── Per-utility analysis ───────────────────────────────────────
    print("=" * 62)
    print("  PER-UTILITY ANALYSIS")
    print("=" * 62)

    results = {}
    for utility in UTILITIES:
        active = [r for r in rows if r["utility"] == utility and not r["exclude"]]
        excluded = [r for r in rows if r["utility"] == utility and r["exclude"]]

        # For Trash, skip $0 months in averages (those were no-bill months)
        active_nonzero = [r for r in active if r["amount"] > 0]
        values = [r["amount"] for r in active_nonzero]

        if not values:
            print(f"\n  {utility.upper()}: no active data\n")
            continue

        s = stats(values)
        vbd = {r["date"]: r["amount"] for r in active_nonzero}
        roll12 = rolling_avg(vbd, 12)
        high_months, low_months = seasonal_pattern(vbd)

        # Recommended: max(avg + 1.0*std, p80) rounded up to nearest dollar
        raw_rec = max(s["avg"] + CUSHION_STDDEV * s["std"], s["p80"])
        recommended = math.ceil(raw_rec)

        buffer_needed = max(0.0, s["max"] - recommended)

        results[utility] = {
            **s,
            "roll12": roll12,
            "recommended": recommended,
            "buffer": buffer_needed,
            "high_months": high_months,
            "low_months": low_months,
            "active": active,
            "excluded": excluded,
        }

        print(f"\n  {utility.upper()}")
        print(f"  {'─'*55}")
        print(f"    Months of data:   {s['n']} (active, non-zero)")
        print(f"    Average:          ${s['avg']:.2f}")
        print(f"    Median:           ${s['median']:.2f}")
        print(f"    Std deviation:    ${s['std']:.2f}")
        print(f"    Low month:        ${s['min']:.2f}")
        print(f"    High month:       ${s['max']:.2f}  ← worst case you saw")
        print(f"    75th percentile:  ${s['p75']:.2f}")
        print(f"    80th percentile:  ${s['p80']:.2f}")
        print(f"    Rolling 12-mo avg:${roll12:.2f}")
        print(f"    Seasonal high:    {high_months}")
        print(f"    Seasonal low:     {low_months}")
        print(f"    ── Funding recommendation ──────────────────────")
        print(f"    Formula:          avg (${s['avg']:.2f}) + 1.0×std (${s['std']:.2f})")
        print(f"    Raw:              ${raw_rec:.2f}  →  rounded up to ${recommended}")
        if buffer_needed > 0:
            print(f"    Buffer for peak:  ${buffer_needed:.2f}  (if {utility} ever hits ${s['max']:.2f} again)")
        else:
            print(f"    Buffer for peak:  $0  (funding target already covers your peak)")
        if excluded:
            print(f"    Excluded rows:    {len(excluded)} (marked in bills.csv)")

        generate_chart(utility, active, excluded, recommended, s["avg"], s)

    generate_overview_chart(results)

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print("  FLEX FUNDING SUMMARY")
    print("=" * 62)
    total_funding = 0
    total_buffer = 0.0
    for utility in UTILITIES:
        if utility not in results:
            continue
        r = results[utility]
        print(f"  {utility:<12}  fund ${r['recommended']:>3}/mo   "
              f"(peak buffer: ${r['buffer']:.2f})")
        total_funding += r["recommended"]
        total_buffer += r["buffer"]

    print("  " + "─" * 55)
    print(f"  {'TOTAL':<12}  fund ${total_funding:>3}/mo   "
          f"(keep ${total_buffer:.2f} parked in account)")
    print()
    print("  INTERPRETATION")
    print(f"  • Fund the flex account ${total_funding}/month, every month.")
    print(f"  • Keep a standing buffer of ${total_buffer:.2f} in the account.")
    print(f"    This covers the gap between your standard funding and")
    print(f"    the absolute peak observed for each utility.")
    print(f"  • Each month's leftover sweeps to savings.")
    print()
    print(f"  Cushion logic: avg + 1.0 × std dev (~84th percentile).")
    print(f"  You said lean conservative — this setting means roughly")
    print(f"  5 out of 6 months you'll have money left over.")
    print("=" * 62 + "\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        analyze()
        return

    cmd = args[0].lower()

    if cmd == "add":
        if len(args) < 4:
            print("Usage: python analyze.py add <Utility> <YYYY-MM> <amount> [notes]")
            sys.exit(1)
        notes = " ".join(args[4:]) if len(args) > 4 else ""
        add_bill(args[1], args[2], args[3], notes)
        print()
        analyze()

    elif cmd == "exclude":
        if len(args) < 3:
            print("Usage: python analyze.py exclude <Utility> <YYYY-MM>")
            sys.exit(1)
        toggle_exclude(args[1], args[2])
        print()
        analyze()

    else:
        print(f"Unknown command '{cmd}'. Commands: add, exclude")
        sys.exit(1)


if __name__ == "__main__":
    main()
