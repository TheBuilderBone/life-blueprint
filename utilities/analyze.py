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

def generate_chart(utility, active_rows, excluded_rows, recommended, avg_val):
    """Save a line chart PNG for this utility. Uses only stdlib + matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import datetime
    except ImportError:
        print("  [charts skipped — install matplotlib: pip install matplotlib]")
        return

    os.makedirs(CHARTS_DIR, exist_ok=True)

    def to_date(s):
        return datetime.datetime.strptime(s, "%Y-%m")

    dates = [to_date(r["date"]) for r in active_rows]
    amounts = [r["amount"] for r in active_rows]

    excl_dates = [to_date(r["date"]) for r in excluded_rows]
    excl_amounts = [r["amount"] for r in excluded_rows]

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(dates, amounts, "o-", linewidth=2, color="#2a7ac7", label="Monthly bill", zorder=3)
    if excl_dates:
        ax.scatter(excl_dates, excl_amounts, color="gray", marker="x", s=80,
                   linewidths=2, label="Excluded (outlier)", zorder=4)
    ax.axhline(avg_val, color="#f5a623", linestyle="--", linewidth=1.4,
               label=f"Avg: ${avg_val:.2f}")
    ax.axhline(recommended, color="#d0021b", linestyle="--", linewidth=1.6,
               label=f"Funding target: ${recommended:.0f}/mo")
    ax.set_title(f"{utility} — Monthly Cost (your share)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Cost ($)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45, ha="right")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out_path = os.path.join(CHARTS_DIR, f"{utility.lower()}.png")
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"  Chart saved: charts/{utility.lower()}.png")


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

        generate_chart(utility, active, excluded, recommended, s["avg"])

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
