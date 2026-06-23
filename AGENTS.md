# AGENTS.md

## Project overview

This repository is a collection of standalone Python 3 scripts for Amazon
US e-commerce market research (women's sweaters & T-shirts). There is **no
server, database, or long-running service** — each script is a one-shot batch
job that writes text/CSV/JSON reports to local folders. "Running the app" means
executing a script and inspecting the generated report files.

Two kinds of scripts:

- **Scraping + analysis** (`amazon_sweater_analysis.py`, `amazon_tshirt_analysis.py`,
  `tshirt_seasonal_analysis.py`): drive headless Chrome via Selenium to scrape
  Amazon Best Sellers (and Google Trends via `pytrends` for the seasonal one).
  Require a Chrome browser + live outbound internet. Amazon actively bot-blocks,
  so live runs can be slow/partial/empty depending on network conditions.
- **Report-only** (`amazon_analysis/generate_report.py`, `tshirt_seasonal_report.py`,
  `new_product_plan_130days.py`): pure computation over the committed CSV/JSON
  data in `amazon_analysis/`, `tshirt_analysis/`, `tshirt_seasonal/`. Run fully
  offline; only need `pandas` (or stdlib). Best for quick verification.

## Cursor Cloud specific instructions

- **System Python is externally managed (PEP 668).** Install packages with
  `python3 -m pip install --break-system-packages ...`. The update script handles
  this automatically; if installing manually, include the flag.
- **Google Chrome is preinstalled** at `/usr/local/bin/google-chrome`. Do not
  install a browser. `webdriver-manager` downloads a matching ChromeDriver at
  runtime (needs internet), so the first Selenium run makes a network call.
- **Selenium must run headless** in this environment. Use
  `--headless=new --no-sandbox --disable-dev-shm-usage` Chrome options (the
  scraping scripts already set headless + `--no-sandbox`).
- **Several scripts hardcode absolute `/workspace/...` output paths** (e.g.
  `OUTPUT_DIR = "/workspace/tshirt_analysis"`, report paths). Run scripts from
  the repo root at `/workspace`, and expect outputs to be written under
  `/workspace/...`.
- **Fastest way to confirm the environment works** (no network needed):
  `python3 new_product_plan_130days.py`, `python3 amazon_analysis/generate_report.py`,
  and `python3 tshirt_seasonal_report.py` — these regenerate reports from
  committed data.
- **The code currently lives on a feature branch, not `main`.** `main` only
  contains a placeholder `README.md`. The update script installs the required
  packages directly (not from a manifest) so it works regardless of which branch
  is checked out.
- There is no lint config and no automated test suite in this repo.
