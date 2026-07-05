# AlphaSync

AlphaSync is the momentum strategy product.

It owns:

- Momentum rotation / V6 DCA strategy engine.
- Macro regime, dual-gate, cross-sectional collapse, and state-driven rotation logic.
- Web dashboard, Supabase schema, and Vercel deployment configuration.
- Strategy run publishing and generated web data.

## Structure

- `python/` - momentum strategy engine (`main.py`), the daily exit monitor (`monitor/`, live), and a separate A-share rotation strategy (`main_ashare.py`).
- `web/` - Next.js application.
- `scripts/` - data generation (`generate_data.py`) and Supabase publishing (`publish_strategy_run.py`).
- `tests/` - AlphaSync strategy tests.
- `docs/` - architecture documentation (`Architecture.md`).
- `output/` - generated strategy outputs (CSV / state).
- `cache/` - local price cache (`price_cache/`) and yfinance tz cache; regenerable, git-ignored.

## Automation (GitHub Actions)

- `weekly_web_data_refresh.yml` - Fri 22:30 UTC -> `scripts/generate_data.py` -> commit `web/data`.
- `daily_exit_monitor.yml` - Mon-Fri 21:30 UTC -> `python/monitor/daily_exit_monitor.py`.

## Common Commands

```powershell
python -m compileall -q python scripts tests
python python/main.py --run-mode full        # full backtest -> output/
python scripts/generate_data.py              # output/ + cache/ -> web/data/*.json
python -m pytest tests/ -q                   # 32 tests
cd web
npm install
npm run build
```
