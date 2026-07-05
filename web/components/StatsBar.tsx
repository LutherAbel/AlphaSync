import type { Stats } from '@/lib/types'

function fmt(n: number, decimals = 1) {
  return n.toFixed(decimals)
}

function fmtMoney(n: number) {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}

interface Props {
  stats: Stats
  mode?: 'money' | 'nav'
}

export default function StatsBar({ stats, mode = 'money' }: Props) {
  const sign = (n: number) => (n >= 0 ? '+' : '')

  if (mode === 'nav') {
    return (
      <div className="stats-bar">
        TWR CAGR {fmt(stats.twrCagr)}%
        {'  |  '}SPY NAV {fmt(stats.twrSpyCagr)}%
        {'  |  '}Alpha {sign(stats.twrAlpha)}{fmt(stats.twrAlpha)}%
        {'  |  '}MDD {fmt(stats.twrMdd)}%
        {'  |  '}Sharpe {fmt(stats.twrSharpe, 2)}
      </div>
    )
  }

  return (
    <div className="stats-bar">
      Account CAGR {fmt(stats.cagr)}%
      {'  |  '}SPY Account {fmt(stats.spyCagr)}%
      {'  |  '}Equity {fmtMoney(stats.endingEquity)}
      {'  |  '}SPY Equity {fmtMoney(stats.endingSpyEquity)}
      {'  |  '}Injected {fmtMoney(stats.totalInjected)}
      {'  |  '}Net Profit {fmtMoney(stats.netProfit)}
    </div>
  )
}
