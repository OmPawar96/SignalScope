# SignalScope
#### Video Demo: https://youtu.be/0VaU5tN12S4?si=934YtwDRRTqWNAKn
#### Description:

SignalScope is a command-line tool, written entirely in Python, that helps a beginner understand the financial health of a company listed on the NSE or BSE. You type a stock symbol such as `TCS`, and instead of dumping raw numbers on the screen, SignalScope turns each one into a colour-coded signal: **green** for healthy, **yellow** for "look closer", **red** for a concern, and **grey** when the data is not available. A short sentence next to every signal explains the reading, for example `-₹800 Cr - net loss` or `66.67% - debt rose while profit fell`.

I built it because financial statements are hard to read when you are new to investing. A table of revenue, borrowings and cash flow tells a beginner very little unless they already know which numbers matter and what "good" looks like. SignalScope is meant as an educational research aid. It does not predict prices and never says buy or sell. The last line of every report says so.

## What it shows

* **Price and ratios:** P/E, P/B, return on equity (ROE) and return on capital employed (ROCE).
* **Financials:** revenue, operating profit, net profit and EPS growth; net and operating margin; whether the company is profitable.
* **Cash flow:** operating cash flow, cash conversion (how much profit became real cash) and free cash flow.
* **Debt and safety:** debt-to-equity, whether debt rose or fell, interest cover and the current ratio.
* **Technicals:** only two lines, RSI and price versus the 20-day average, for short-term context.
* **Summary:** a count of positive, caution, concern and unavailable signals.
* **What-if:** enter an old investment amount and the share price back then, and see what it would be worth today.

## How to run it

Install the only dependency with `pip install requests`. The data comes from the BharatStock API, so you need a free API key. Store it in an environment variable and never write it into the code:

```
set BHARAT_API_KEY=your_key_here        (Windows Command Prompt)
export BHARAT_API_KEY=your_key_here     (macOS / Linux)
python project.py
```

The free plan allows about 60 requests per day, and one report uses three.

## Files

**`project.py`** contains the whole program. It is organised into groups of functions:

* *Helpers.* `get_json()` makes an API request with a timeout and prints a clear message for the common failures: an invalid key (401), an unknown ticker (404), the daily limit (429), no internet or a timeout. `unwrap()` removes the `{"data": ...}` wrapper the API uses on list endpoints. `pct()`, `ratio()` and `rnd()` do safe arithmetic that return `None` instead of crashing when a value is missing or a denominator is zero. `fmt_cr()` and `total_debt()` format rupee amounts in crore and add up borrowings.
* *Signal functions.* Each takes one number and returns a `(colour, message)` pair. `higher_is_better()` is a generic rule (below one threshold is red, below another is yellow, otherwise green) used for growth, margins, ROE, ROCE and the current ratio. Others, such as `pe_signal()`, `debt_signal()` and `cash_conversion_signal()`, are written by hand because "higher is better" does not fit them. A very low P/E is not simply good, and a company with negative equity needs its own warning.
* *Data sections.* `stock()`, `financials()` and `indicators()` fetch one endpoint each and build a dictionary of labels and signals.
* *Output.* `show()` prints a section and counts how many signals of each colour it printed, `show_summary()` prints the totals, and `main()` ties everything together.

**`test_project.py`** holds `pytest` tests for the pure functions that need no internet: `pct`, `ratio`, `rnd`, `higher_is_better`, and the signal functions.

## Design decisions

**Missing data is never treated as zero.** If the API leaves out a borrowing figure, treating it as zero would label a company debt-free by accident. So `total_debt()` returns `None` if either part is missing, and the signal shows grey "not available".

**Signals return data, not colours already applied.** Each signal function returns a plain `(colour, message)` pair, and only `show()` applies the colour. This keeps the logic easy to test, because `pe_signal(-5)` can be checked without a terminal.

**Thresholds are rules of thumb.** Cut-offs like "ROE above 15% is strong" are common guidelines, not facts, and they vary by industry. Banks and NBFCs in particular do not fit the debt and liquidity rules, because borrowing is their business. The README and the code comments say so, and the numbers are easy to change in one place.

**No single score or verdict.** I considered a combined score but decided against it. One number would hide the reasoning and could look like advice. A count of signals plus the explanation beside each one keeps the judgement with the reader.

**One data source.** I first planned to combine several APIs, but joining different providers meant mismatched units and periods. I settled on a single provider to keep v1 reliable.

**Trimmed output.** An early version printed every raw field. I removed numbers that do not help a beginner judge a company, such as the 52-week range and extra indicator lines, so every line on screen is a signal worth reading.