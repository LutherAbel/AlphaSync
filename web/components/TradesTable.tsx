'use client'
import { useState } from 'react'
import type { Trade, Holding } from '@/lib/types'

interface Props {
  trades: Trade[]
  holdings: Holding[]
}

const SHOW_OPTIONS = [20, 50, 100, 999999]
const SHOW_LABELS  = ['20', '50', '100', 'All']

const TH: React.CSSProperties = {
  padding: '10px 12px',
  borderBottom: '1px solid #2a2a40',
  color: '#78909C',
  textTransform: 'uppercase',
  fontSize: '0.78em',
  letterSpacing: '.05em',
  fontWeight: 500,
  textAlign: 'left',
  whiteSpace: 'nowrap',
}
const TD: React.CSSProperties = {
  padding: '9px 12px',
  borderBottom: '1px solid #1a1a2e',
  verticalAlign: 'middle',
}

export default function TradesTable({ trades, holdings }: Props) {
  const [showN, setShowN] = useState(20)

  // Open rows from holdings (sorted first_entry_date desc)
  const openRows = [...holdings].sort((a, b) => b.first_entry_date.localeCompare(a.first_entry_date))

  // Closed rows (sorted entry_date desc), limited by showN
  const closedRows = [...trades]
    .sort((a, b) => b.entry_date.localeCompare(a.entry_date))
    .slice(0, showN === 999999 ? undefined : showN)

  return (
    <div>
      {/* Controls */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
                    gap: 8, marginBottom: 12, fontSize: '0.82em', color: '#78909C' }}>
        <label>Show closed&nbsp;</label>
        <select
          value={showN}
          onChange={e => setShowN(Number(e.target.value))}
          style={{
            background: '#252538', color: '#CFD8DC',
            border: '1px solid #37474F', borderRadius: 6,
            padding: '4px 10px', fontSize: '0.82em', cursor: 'pointer',
          }}
        >
          {SHOW_OPTIONS.map((v, i) => (
            <option key={v} value={v}>{SHOW_LABELS[i]}</option>
          ))}
        </select>
      </div>

      <div className="table-wrap">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.91em' }}>
          <thead>
            <tr>
              {['Ticker','Sleeve','Entry Date','Entry $','Exit $','Shares','Exit Date','Reason','PnL %','PnL $'].map(col => (
                <th key={col} style={{ ...TH, textAlign: ['PnL %','PnL $','Shares'].includes(col) ? 'right' : 'left' }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* Open positions */}
            {openRows.map(h => (
              <tr key={`open-${h.ticker}`} style={{ background: 'rgba(27,94,32,0.10)' }}>
                <td style={TD}>
                  <b>{h.ticker}</b>
                  <span style={{ background:'#1B5E20', color:'#69F0AE',
                                 padding:'1px 7px', borderRadius:4, fontSize:'0.74em', marginLeft:6 }}>
                    OPEN
                  </span>
                </td>
                <td style={{ ...TD, color: '#90A4AE' }}>{h.sleeve}</td>
                <td style={{ ...TD, color: '#B0BEC5' }}>{h.first_entry_date}</td>
                <td style={TD}>${h.avg_cost.toFixed(2)}</td>
                <td style={{ ...TD, color: '#546E7A' }}>—</td>
                <td style={{ ...TD, textAlign: 'right' }}>{Math.round(h.shares)}</td>
                <td style={{ ...TD, color: '#4CAF50', fontSize: '0.82em' }}>Holding</td>
                <td style={{ ...TD, color: '#546E7A' }}>—</td>
                <td style={{ ...TD, textAlign: 'right', color: '#546E7A' }}>—</td>
                <td style={{ ...TD, textAlign: 'right', color: '#546E7A' }}>—</td>
              </tr>
            ))}

            {/* Closed trades */}
            {closedRows.map((t, i) => {
              const pos = t.pnl >= 0
              const pc  = pos ? '#00E676' : '#FF5252'
              return (
                <tr key={i}>
                  <td style={TD}><b>{t.ticker}</b></td>
                  <td style={{ ...TD, color: '#90A4AE' }}>long</td>
                  <td style={{ ...TD, color: '#B0BEC5' }}>{t.entry_date}</td>
                  <td style={TD}>${t.entry_price.toFixed(2)}</td>
                  <td style={TD}>${t.exit_price.toFixed(2)}</td>
                  <td style={{ ...TD, textAlign: 'right' }}>{Math.round(t.shares)}</td>
                  <td style={{ ...TD, color: '#78909C', fontSize: '0.83em' }}>{t.exit_date}</td>
                  <td style={{ ...TD, color: '#546E7A', fontSize: '0.82em' }}>{t.exit_reason}</td>
                  <td style={{ ...TD, textAlign: 'right', color: pc }}>
                    {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                  </td>
                  <td style={{ ...TD, textAlign: 'right', color: pc, fontWeight: 600 }}>
                    {t.pnl >= 0 ? '+' : ''}${Math.abs(t.pnl).toFixed(0)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
