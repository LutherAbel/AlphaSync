# AlphaSync

AlphaSync verifies investment strategies against the academic literature and
publishes the results as public research notes at alphasync.capital.

Note No. 1 audits our own strategy: a literature-based momentum implementation
(Jegadeesh-Titman 1993, Barroso-Santa-Clara 2015) on a point-in-time
Nasdaq-100 universe. Every number on the site is recomputed from primary data
by the pipeline in `research/`; nothing is hand-typed. Trials, failures, and
narrative corrections are logged in `docs/FactorSpec.md`.

## Structure

- `research/` - data fetch (Tiingo, SEC EDGAR, Ken French), factor pipeline
  (`build_factor.py`), trials, and the site data export (`export_note_data.py`).
- `web/` - Next.js research-note site (static; no backend, no auth).
- `docs/FactorSpec.md` - locked specification + pre-registered trial changelog.
- `output/`, `research/output/` - pipeline outputs (tracked where the site needs them).

## Automation (GitHub Actions)

- `monthly_factor_refresh.yml` - 1st of month 22:30 UTC: refresh prices ->
  rebuild sleeve -> re-export site data -> commit -> Vercel auto-deploys.
  Requires repo secret `TIINGO_API_KEY`.

## Common Commands

```powershell
python research/fetch_data.py --refresh   # update price cache (needs TIINGO_API_KEY)
python research/build_factor.py           # rebuild sleeve + holdings
python research/export_note_data.py       # regenerate web/data/factor_note.json
cd web; npm install; npm run build
```

## History

The original v6 momentum-rotation engine (regime gates, dual-lock exits,
Supabase-backed personal plans) was retired in July 2026 after its backtest
was found to use a hindsight-selected universe. The code lives in git history
before commit `retire-v6`.
