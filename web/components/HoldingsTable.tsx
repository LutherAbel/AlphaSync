import type { Holding } from '@/lib/types'

interface Allocation {
  targetPct: number
  suggestedAmount: number
}

interface Props {
  holdings: Holding[]
  locked?: boolean
  allocations?: Record<string, Allocation>
  onRequestUnlock?: () => void
}

function fmtMoney(n: number) {
  return `$${Math.round(n).toLocaleString('en-US')}`
}

export default function HoldingsTable({ holdings, locked = false, allocations, onRequestUnlock }: Props) {
  if (!holdings.length) {
    return <p style={{ color: 'var(--text-muted)', fontSize: '0.85em' }}>No current holdings.</p>
  }

  const rows = holdings
  const gatedStartIndex = 4
  const hasGateOverlay = locked && rows.length > gatedStartIndex

  return (
    <div className={`table-wrap holdings-wrap${hasGateOverlay ? ' is-gated' : ''}`}>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>First Entry</th>
            <th>Avg Cost</th>
            <th>Current Price</th>
            <th>Shares</th>
            {allocations && <th>Target</th>}
            {allocations && <th>Sync Amount</th>}
            <th>Sleeve</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h, index) => {
            const isGated = locked && index >= 4
            const allocation = isGated ? null : allocations?.[h.ticker]

            return (
              <tr key={h.ticker} className={isGated ? 'holdings-row-gated' : ''}>
                <td style={{ color: isGated ? 'var(--text-muted)' : 'var(--accent)', fontWeight: 600 }}>
                  {isGated ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      <span aria-hidden="true">🔒</span>
                      <span>••••</span>
                    </span>
                  ) : (
                    h.ticker
                  )}
                </td>
                <td>{isGated ? '--' : h.first_entry_date}</td>
                <td>{isGated ? '--' : `$${h.avg_cost.toFixed(2)}`}</td>
                <td>{isGated ? '--' : `$${h.current_price.toFixed(2)}`}</td>
                <td>{isGated ? '--' : h.shares.toFixed(1)}</td>
                {allocations && <td>{allocation ? `${allocation.targetPct.toFixed(1)}%` : '--'}</td>}
                {allocations && <td>{allocation ? fmtMoney(allocation.suggestedAmount) : '--'}</td>}
                <td>{isGated ? 'private' : h.sleeve}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {hasGateOverlay && (
        <button type="button" className="holdings-gate-overlay" onClick={onRequestUnlock}>
          <span className="lock-icon" aria-hidden="true">🔒</span>
          <span>註冊以解鎖完整持倉</span>
        </button>
      )}
    </div>
  )
}
