import os
import sys
from collections import Counter
from urllib.parse import quote

import requests

BASE = "https://bharatstockapi.com/v1/stocks"
CRORE = 1e7

RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GREY = "\033[90m"

# Makes colours work in the Windows Command Prompt too.
if os.name == "nt":
    os.system("")

HTTP_MESSAGES = {
    401: "API key missing or invalid. Check your BHARAT_API_KEY.",
    404: "Ticker not found. Use the exchange symbol, e.g. TCS or RELIANCE.",
    422: "The API rejected the request parameters.",
    429: "Daily request limit reached (Free plan: 60/day, resets at UTC midnight).",
}


# ---------- small helpers ----------

def get_json(url, headers, params=None):
    """Return parsed JSON, or None if the request fails (and say why)."""
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        code = e.response.status_code
        print(f"[error] {HTTP_MESSAGES.get(code, f'HTTP {code} from the API')}")
    except requests.Timeout:
        print("[error] The request timed out.")
    except requests.ConnectionError:
        print("[error] Could not connect. Check your internet connection.")
    except requests.RequestException as e:
        print(f"[error] Request failed: {e}")
    except ValueError:
        print("[error] The API did not return valid JSON.")
    return None


def unwrap(payload):
    """The API wraps list results in {'data': ...}; return the inside if present."""
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def pct(old, new):
    """Percentage change old -> new, or None if it can't be computed."""
    if not old or new is None:
        return None
    return (new - old) / abs(old) * 100


def ratio(a, b):
    """a / b, or None if a is missing or b is missing/zero."""
    if a is None or not b:
        return None
    return a / b


def rnd(value, digits=2):
    return None if value is None else round(value, digits)


def fmt_cr(value):
    """Rupees -> '₹1,234 Cr' (keeps the minus sign), or None if missing."""
    if value is None:
        return None
    crore = value / CRORE
    sign = "-" if crore < 0 else ""
    return f"{sign}₹{abs(crore):,.0f} Cr"


def total_debt(year):
    """Current + non-current borrowings, or None if either part is missing."""
    non_current = year.get("borrowings_non_current")
    current = year.get("borrowings_current")
    if non_current is None or current is None:
        return None
    return non_current + current


def colored_text(text, color):
    return f"{color}{text}{RESET}"


# ---------- signals: each returns (colour, message) ----------
# Thresholds are rules of thumb for non-financial companies. They vary by
# industry, and banks/NBFCs work differently (their debt is their business).

NOT_AVAILABLE = (GREY, "not available")


def higher_is_better(value, red_below, green_from, unit="",
                     words=("weak", "moderate", "strong")):
    """Generic rule: below red_below = red, below green_from = yellow, else green."""
    if value is None:
        return NOT_AVAILABLE
    bad, middle, good = words
    text = f"{value}{unit}"
    if value < red_below:
        return (RED, f"{text} - {bad}")
    if value < green_from:
        return (YELLOW, f"{text} - {middle}")
    return (GREEN, f"{text} - {good}")


def growth_signal(growth_pct):
    return higher_is_better(growth_pct, 0, 5, "%", ("shrinking", "slow growth", "growing"))


def margin_signal(margin_pct):
    return higher_is_better(margin_pct, 0, 5, "%", ("loss-making", "thin margin", "healthy margin"))


def operating_margin_signal(margin_pct):
    return higher_is_better(margin_pct, 0, 10, "%", ("operating loss", "thin margin", "healthy margin"))


def return_signal(value):
    """ROE / ROCE."""
    return higher_is_better(value, 8, 15, "%", ("weak returns", "average returns", "strong returns"))


def current_ratio_signal(value):
    return higher_is_better(value, 1, 1.5, "", ("short-term bills exceed short-term assets",
                                                "adequate", "comfortable"))


def interest_cover_signal(operating_profit, finance_costs):
    if operating_profit is None or finance_costs is None:
        return NOT_AVAILABLE
    if finance_costs == 0:
        return (GREEN, "no interest costs reported")
    cover = rnd(operating_profit / finance_costs)
    return higher_is_better(cover, 1.5, 3, "x", ("struggling to cover interest",
                                                 "tight", "comfortable"))


def pe_signal(pe):
    if pe is None:
        return NOT_AVAILABLE
    if pe <= 0:
        return (RED, f"{pe} - negative: loss-making, so P/E isn't meaningful")
    if pe > 40:
        return (YELLOW, f"{pe} - very high: expectations are elevated, check earnings growth")
    if pe < 10:
        return (YELLOW, f"{pe} - very low: could be undervalued, or the business may have problems")
    return (GREEN, f"{pe} - moderate: a common range for mature businesses")


def pb_signal(pb):
    if pb is None:
        return NOT_AVAILABLE
    if pb <= 0:
        return (RED, f"{pb} - negative: equity is wiped out or negative")
    if pb < 1:
        return (YELLOW, f"{pb} - below book value: cheap, or the market sees trouble")
    if pb > 5:
        return (YELLOW, f"{pb} - high premium to book value")
    return (GREEN, f"{pb} - reasonable")


def profit_signal(net_profit):
    if net_profit is None:
        return NOT_AVAILABLE
    if net_profit > 0:
        return (GREEN, f"{fmt_cr(net_profit)} - profitable")
    if net_profit < 0:
        return (RED, f"{fmt_cr(net_profit)} - net loss")
    return (YELLOW, f"{fmt_cr(net_profit)} - break-even")


def eps_signal(eps):
    if eps is None:
        return NOT_AVAILABLE
    text = f"{'-' if eps < 0 else ''}₹{abs(eps)} per share"
    if eps > 0:
        return (GREEN, f"{text} - positive")
    if eps < 0:
        return (RED, f"{text} - negative")
    return (YELLOW, f"{text} - zero")


def operating_cash_signal(ocf):
    if ocf is None:
        return NOT_AVAILABLE
    if ocf > 0:
        return (GREEN, f"{fmt_cr(ocf)} - business generates cash")
    return (RED, f"{fmt_cr(ocf)} - business burns cash")


def cash_conversion_signal(ocf, net_profit):
    """How much of the profit turns into real cash."""
    if ocf is None or net_profit is None:
        return NOT_AVAILABLE
    if net_profit <= 0:
        if ocf > 0:
            return (YELLOW, "cash positive despite no profit")
        return (RED, "no profit and no cash")
    conversion = rnd(ocf / net_profit)
    return higher_is_better(conversion, 0.5, 0.8, "x", ("profit isn't turning into cash",
                                                        "partly backed by cash",
                                                        "profit is backed by cash"))


def free_cash_signal(ocf, capex):
    if ocf is None or capex is None:
        return NOT_AVAILABLE
    fcf = ocf - capex
    if fcf > 0:
        return (GREEN, f"{fmt_cr(fcf)} - cash left after investing")
    if ocf > 0:
        return (YELLOW, f"{fmt_cr(fcf)} - investing more than it earns")
    return (RED, f"{fmt_cr(fcf)} - cash shortfall")


def debt_signal(debt_to_equity):
    if debt_to_equity is None:
        return NOT_AVAILABLE
    if debt_to_equity < 0:
        return (RED, f"{debt_to_equity} - negative equity, liabilities exceed assets")
    if debt_to_equity < 0.3:
        return (GREEN, f"{debt_to_equity} - low debt")
    if debt_to_equity > 2:
        return (RED, f"{debt_to_equity} - very high debt")
    return (YELLOW, f"{debt_to_equity} - moderate debt")


def debt_change_signal(debt_change_pct, profit_growth_pct):
    if debt_change_pct is None:
        return NOT_AVAILABLE
    text = f"{debt_change_pct}%"
    if debt_change_pct <= 0:
        return (GREEN, f"{text} - debt did not increase")
    if profit_growth_pct is not None and profit_growth_pct < 0:
        return (RED, f"{text} - debt rose while profit fell")
    if debt_change_pct > 25:
        return (RED, f"{text} - debt rose sharply")
    return (YELLOW, f"{text} - debt rose")


def rsi_signal(rsi):
    if rsi is None:
        return NOT_AVAILABLE
    if rsi > 70:
        return (YELLOW, f"{rsi} - overbought: price has risen fast")
    if rsi < 30:
        return (YELLOW, f"{rsi} - oversold: price has fallen fast")
    return (GREEN, f"{rsi} - neutral")


def trend_signal(close, sma):
    if close is None or sma is None:
        return NOT_AVAILABLE
    if close >= sma:
        return (GREEN, f"₹{close} vs average ₹{sma} - above")
    return (YELLOW, f"₹{close} vs average ₹{sma} - below")


# ---------- data sections ----------

def get_ratios(name, headers):
    """Raw ratios for one stock (a dictionary), or None."""
    return unwrap(get_json(f"{BASE}/{quote(name, safe='')}/ratios", headers))


def stock(data):
    """Turn the raw ratios dictionary into signals."""
    if not data:
        return None

    return {
        "Price": f"₹{data.get('price')}  (as of {data.get('as_of_date')})",
        "P/E ratio": pe_signal(data.get("pe_ratio")),
        "P/B ratio": pb_signal(data.get("pb_ratio")),
        "Return on equity": return_signal(data.get("roe")),
        "Return on capital": return_signal(data.get("roce")),
    }


def financials(name, headers):
    payload = get_json(
        f"{BASE}/{quote(name, safe='')}/financials", headers, {"period_type": "annual"}
    )
    years = unwrap(payload)
    if not years:
        return None

    # newest first, regardless of how the API orders them
    years = sorted(years, key=lambda y: y.get("period_end_date") or "", reverse=True)
    now = years[0]
    before = years[1] if len(years) > 1 else {}   # {} -> growth shows "not available"

    debt_now = total_debt(now)
    debt_before = total_debt(before) if before else None

    net_profit = now.get("net_profit")
    ocf = now.get("cash_flow_operating")

    margin = ratio(net_profit, now.get("revenue"))
    op_margin = ratio(now.get("operating_profit"), now.get("revenue"))
    debt_to_equity = rnd(ratio(debt_now, now.get("total_equity")))

    net_profit_growth = rnd(pct(before.get("net_profit"), net_profit))
    debt_change = rnd(pct(debt_before, debt_now))

    return {
        "Fiscal year": now.get("fiscal_year"),
        "Revenue growth": growth_signal(rnd(pct(before.get("revenue"), now.get("revenue")))),
        "Operating profit growth": growth_signal(
            rnd(pct(before.get("operating_profit"), now.get("operating_profit")))
        ),
        "Net profit": profit_signal(net_profit),
        "Net profit growth": growth_signal(net_profit_growth),
        "Net profit margin": margin_signal(None if margin is None else rnd(margin * 100)),
        "Operating margin": operating_margin_signal(None if op_margin is None else rnd(op_margin * 100)),
        "EPS": eps_signal(now.get("eps")),
        "EPS growth": growth_signal(rnd(pct(before.get("eps"), now.get("eps")))),
        "Operating cash flow": operating_cash_signal(ocf),
        "Cash conversion": cash_conversion_signal(ocf, net_profit),
        "Free cash flow": free_cash_signal(ocf, now.get("capex")),
        "Debt to equity": debt_signal(debt_to_equity),
        "Debt change": debt_change_signal(debt_change, net_profit_growth),
        "Interest cover": interest_cover_signal(now.get("operating_profit"), now.get("finance_costs")),
        "Current ratio": current_ratio_signal(
            rnd(ratio(now.get("current_assets"), now.get("current_liabilities")))
        ),
    }


def indicators(name, headers):
    # The API returns {"data": [one row per trading day], ...}: a LIST of rows.
    rows = unwrap(
        get_json(
            f"{BASE}/{quote(name, safe='')}/technical-indicators",
            headers,
            {"sma_period": 20, "rsi_period": 14},
        )
    )
    if not rows or not isinstance(rows, list):
        return None

    # pick the newest trading day regardless of how the API orders the rows
    latest = max(rows, key=lambda row: row.get("trade_date") or "")
    return {
        "RSI (14 days)": rsi_signal(latest.get("rsi")),
        "Price vs 20-day average": trend_signal(latest.get("close"), latest.get("sma")),
    }


def what_if(amount, old_price, current_price):
    value = amount * current_price / old_price
    change = rnd(pct(amount, value))
    color = GREEN if change >= 0 else RED
    return {
        "Invested": f"₹{amount:,.2f}",
        "Worth now": (color, f"₹{value:,.2f}"),
        "Change": (color, f"{change:+.2f}%"),
    }


# ---------- input / output ----------

def ask_positive_float(prompt):
    """Keep asking until the user types a number greater than 0."""
    while True:
        try:
            value = float(input(prompt))
        except ValueError:
            print("Please enter a number.")
            continue
        if value > 0:
            return value
        print("Please enter a number greater than 0.")


def show(title, result):
    """Print a section. Returns a Counter of how many signals of each colour."""
    counts = Counter()
    print(f"\n--- {title} ---")
    if result is None:
        print("Data not available")
        return counts
    for key, value in result.items():
        if isinstance(value, tuple):  # (colour, message) from a *_signal function
            color, message = value
            print(f"{key:<26}{colored_text(message, color)}")
            counts[color] += 1
        else:
            print(f"{key:<26}{'N/A' if value is None else value}")
    return counts


def show_summary(counts):
    print("\n--- SUMMARY ---")
    print(colored_text(f"{counts[GREEN]} positive", GREEN), end="   ")
    print(colored_text(f"{counts[YELLOW]} caution", YELLOW), end="   ")
    print(colored_text(f"{counts[RED]} concern", RED), end="   ")
    print(colored_text(f"{counts[GREY]} not available", GREY))
    print("Educational signals only. Not investment advice.")


def main():
    api_key = os.environ.get("BHARAT_API_KEY")
    if not api_key:
        sys.exit("Please set the BHARAT_API_KEY environment variable first.")
    headers = {"X-API-Key": api_key}

    print("WELCOME TO SIGNALSCOPE")
    name = input("Enter the name of the stock you want to analyse: ").strip()
    if not name:
        sys.exit("No stock name entered.")

    totals = Counter()
    ratios = get_ratios(name, headers)
    totals += show("PRICE & RATIOS", stock(ratios))
    totals += show("FINANCIALS", financials(name, headers))
    totals += show("TECHNICALS", indicators(name, headers))
    show_summary(totals)

    price = ratios.get("price") if ratios else None
    if price is not None and input("\nSee what an old investment is worth today? (y/n) ").strip().lower() == "y":
        amount = ask_positive_float("Amount invested (₹): ")
        old_price = ask_positive_float("Share price back then (₹): ")
        show("WHAT IF", what_if(amount, old_price, price))


if __name__ == "__main__":
    main()