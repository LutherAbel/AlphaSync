'use client'
import { useState, useMemo, useEffect } from 'react'
import type { Execution, StrategyBar } from '@/lib/types'

interface Props {
  executions: Execution[]
  bars?: StrategyBar[]
  startDate?: string
  endDate?: string
}

const PAGE_SIZE = 30

export default function ExecutionsTable({ executions, bars = [], startDate, endDate }: Props) {
  const [page, setPage] = useState(0)
  const [pageInput, setPageInput] = useState('1')

  const filteredExecutions = useMemo(() => {
    if (!startDate && !endDate) return executions
    return executions.filter(ex => {
      if (startDate && ex.date < startDate) return false
      if (endDate && ex.date > endDate) return false
      return true
    })
  }, [executions, startDate, endDate])

  const dualGateDates = useMemo(() => {
    const dates = new Set<string>()
    for (const bar of bars) {
      if (bar.dual_gate) dates.add(bar.date)
    }
    return dates
  }, [bars])

  const emergencyExitDates = useMemo(() => {
    const dates = new Set<string>()
    for (const ex of filteredExecutions) {
      const isSell = ex.action === 'SELL' || ex.action === 'REDUCE'
      const isEmergency = ex.reason === 'dual_gate_exit' || ex.reason === 'dual_gate_exit_weekly'
      if (isSell && isEmergency) dates.add(ex.date)
    }
    // Use explicit dual-gate dates as primary source,
    // keep execution-reason dates as backward-compatible fallback.
    return dualGateDates.size > 0 ? dualGateDates : dates
  }, [filteredExecutions, dualGateDates])

  // Net same-date same-ticker buy/sell shares before rendering.
  const grouped = useMemo(() => {
    type NetBucket = {
      ticker: string
      buyShares: number
      buyNotional: number
      sellShares: number
      sellNotional: number
      sellPnlDollar: number
      sellPnlPctWeighted: number
      sellPnlPctWeight: number
    }

    const perDateTicker = new Map<string, NetBucket>()
    for (const ex of filteredExecutions) {
      const k = `${ex.date}::${ex.ticker}`
      if (!perDateTicker.has(k)) {
        perDateTicker.set(k, {
          ticker: ex.ticker,
          buyShares: 0,
          buyNotional: 0,
          sellShares: 0,
          sellNotional: 0,
          sellPnlDollar: 0,
          sellPnlPctWeighted: 0,
          sellPnlPctWeight: 0,
        })
      }
      const b = perDateTicker.get(k)!
      if (ex.action === 'BUY' || ex.action === 'ADD') {
        b.buyShares += ex.shares
        b.buyNotional += ex.shares * ex.price
      } else {
        b.sellShares += ex.shares
        b.sellNotional += ex.shares * ex.price
        if (ex.pnl_dollar != null) b.sellPnlDollar += ex.pnl_dollar
        if (ex.pnl_pct != null) {
          b.sellPnlPctWeighted += ex.pnl_pct * ex.shares
          b.sellPnlPctWeight += ex.shares
        }
      }
    }

    const map = new Map<string, { buys: Execution[]; sells: Execution[] }>()
    for (const [k, b] of Array.from(perDateTicker.entries())) {
      const [date] = k.split('::')
      if (!map.has(date)) map.set(date, { buys: [], sells: [] })
      const g = map.get(date)!

      const netShares = b.buyShares - b.sellShares
      if (netShares === 0) continue

      if (netShares > 0) {
        g.buys.push({
          date,
          ticker: b.ticker,
          action: 'BUY',
          shares: netShares,
          price: b.buyShares > 0 ? b.buyNotional / b.buyShares : 0,
          avg_price_before: null,
          sleeve: 'long',
          reason: 'netted_same_day',
          pnl_pct: null,
          pnl_dollar: null,
        })
      } else {
        const netSellShares = Math.abs(netShares)
        const avgSellPrice = b.sellShares > 0 ? b.sellNotional / b.sellShares : 0
        const avgSellPnlPct = b.sellPnlPctWeight > 0 ? b.sellPnlPctWeighted / b.sellPnlPctWeight : null
        const pnlPerShare = b.sellShares > 0 ? b.sellPnlDollar / b.sellShares : 0
        g.sells.push({
          date,
          ticker: b.ticker,
          action: 'SELL',
          shares: netSellShares,
          price: avgSellPrice,
          avg_price_before: null,
          sleeve: 'long',
          reason: 'netted_same_day',
          pnl_pct: avgSellPnlPct,
          pnl_dollar: b.sellPnlDollar !== 0 ? pnlPerShare * netSellShares : null,
        })
      }
    }

    for (const g of Array.from(map.values())) {
      g.buys.sort((a, b) => a.ticker.localeCompare(b.ticker))
      g.sells.sort((a, b) => a.ticker.localeCompare(b.ticker))
    }

    return Array.from(map.entries())
      .sort((a, b) => (a[0] < b[0] ? 1 : -1))
  }, [filteredExecutions])

  const totalPages = Math.ceil(grouped.length / PAGE_SIZE)
  const pageSlice  = grouped.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  useEffect(() => {
    setPage(0)
    setPageInput('1')
  }, [startDate, endDate])

  useEffect(() => {
    if (totalPages <= 0) {
      if (page !== 0) setPage(0)
      if (pageInput !== '1') setPageInput('1')
      return
    }
    if (page > totalPages - 1) setPage(totalPages - 1)
    const nextInput = String(page + 1)
    if (pageInput !== nextInput) setPageInput(nextInput)
  }, [page, totalPages])

  const commitPageInput = () => {
    const n = Number(pageInput)
    if (!Number.isFinite(n) || pageInput.trim() === '') {
      setPageInput(String(page + 1))
      return
    }
    const next = Math.min(Math.max(1, Math.floor(n)), Math.max(1, totalPages))
    setPage(next - 1)
    setPageInput(String(next))
  }

  const th: React.CSSProperties = {
    padding: '6px 10px', color: 'var(--text-muted)', fontWeight: 600,
    fontSize: '0.78em', textTransform: 'uppercase', letterSpacing: '.04em',
    borderBottom: '1px solid var(--border)', textAlign: 'center', whiteSpace: 'nowrap',
  }
  const td: React.CSSProperties = {
    padding: '5px 10px', fontSize: '0.82em', color: 'var(--text)',
    borderBottom: '1px solid var(--border)', textAlign: 'center', whiteSpace: 'nowrap',
  }
  const dividerTd: React.CSSProperties = {
    ...td, width: 2, padding: 0, background: 'var(--border2)',
  }

  const fmtPrice = (p: number) => `$${p.toFixed(2)}`
  const fmtPct   = (p: number) => {
    const s = (p * 100).toFixed(1) + '%'
    return <span style={{ color: p >= 0 ? 'var(--green)' : 'var(--red)' }}>{p >= 0 ? '+' : ''}{s}</span>
  }
  const fmtDollar = (d: number) => {
    const s = `$${Math.abs(d).toFixed(0)}`
    return <span style={{ color: d >= 0 ? 'var(--green)' : 'var(--red)' }}>{d >= 0 ? '+' : '-'}{s}</span>
  }

  return (
    <div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'auto' }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: 'left' }}>Date</th>
              {/* Buy side */}
              <th style={th}>Ticker</th>
              <th style={th}>Entry $</th>
              <th style={th}>Shares</th>
              {/* divider */}
              <th style={{ ...th, width: 2, padding: 0 }}></th>
              {/* Sell side */}
              <th style={th}>Ticker</th>
              <th style={th}>Exit $</th>
              <th style={th}>Shares</th>
              <th style={th}>PnL %</th>
              <th style={th}>PnL $</th>
            </tr>
          </thead>
          <tbody>
            {pageSlice.length === 0 && (
              <tr>
                <td colSpan={10} style={{ ...td, textAlign: 'center', color: 'var(--text-muted)' }}>
                  這個時間區間沒有執行紀錄
                </td>
              </tr>
            )}
            {pageSlice.map(([date, { buys, sells }]) => {
              const rowspan = Math.max(buys.length, sells.length, 1)
              const rows: React.ReactNode[] = []
              for (let i = 0; i < rowspan; i++) {
                const buy  = buys[i]
                const sell = sells[i]
                rows.push(
                  <tr key={`${date}-${i}`}>
                    {i === 0 && (
                      <td rowSpan={rowspan} style={{ ...td, textAlign: 'left',
                        color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums',
                        verticalAlign: 'top', paddingTop: 8 }}>
                        {date}
                        {emergencyExitDates.has(date) && (
                          <span
                            style={{ marginLeft: 4, color: '#FFA726', fontWeight: 700 }}
                            title="Dual-gate 觸發日"
                          >
                            *
                          </span>
                        )}
                      </td>
                    )}
                    {/* Buy side */}
                    <td style={td}>{buy ? <span style={{ color: 'var(--accent)' }}>{buy.ticker}</span> : ''}</td>
                    <td style={td}>{buy ? fmtPrice(buy.price) : ''}</td>
                    <td style={td}>{buy ? buy.shares : ''}</td>
                    {/* Divider */}
                    {i === 0 && <td rowSpan={rowspan} style={dividerTd} />}
                    {/* Sell side */}
                    <td style={td}>{sell ? <span style={{ color: 'var(--text-muted)' }}>{sell.ticker}</span> : ''}</td>
                    <td style={td}>{sell ? fmtPrice(sell.price) : ''}</td>
                    <td style={td}>{sell ? sell.shares : ''}</td>
                    <td style={td}>{sell?.pnl_pct != null ? fmtPct(sell.pnl_pct) : ''}</td>
                    <td style={td}>{sell?.pnl_dollar != null ? fmtDollar(sell.pnl_dollar) : ''}</td>
                  </tr>
                )
              }
              return rows
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, marginTop: 12 }}>
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            aria-label="Previous page"
            style={{
              width: 34,
              height: 30,
              borderRadius: 8,
              border: '1px solid var(--border2)',
              background: 'var(--surface2)',
              color: 'var(--text)',
              fontSize: '0.9em',
              opacity: page === 0 ? 0.4 : 1,
            }}
          >
            ←
          </button>
          <input
            type="number"
            min={1}
            max={Math.max(1, totalPages)}
            value={pageInput}
            onChange={e => {
              const v = e.target.value
              setPageInput(v)
            }}
            onBlur={commitPageInput}
            onKeyDown={e => {
              if (e.key !== 'Enter') return
              commitPageInput()
            }}
            style={{
              width: 42,
              background: 'var(--surface2)',
              border: '1px solid var(--border2)',
              borderRadius: 8,
              color: 'var(--text)',
              padding: '5px 6px',
              fontSize: '0.82em',
              textAlign: 'center',
              fontWeight: 600,
            }}
          />
          <span style={{ color: 'var(--text-muted)', fontSize: '0.85em', alignSelf: 'center' }}>
            / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
            aria-label="Next page"
            style={{
              width: 34,
              height: 30,
              borderRadius: 8,
              border: '1px solid var(--border2)',
              background: 'var(--surface2)',
              color: 'var(--text)',
              fontSize: '0.9em',
              opacity: page === totalPages - 1 ? 0.4 : 1,
            }}
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
