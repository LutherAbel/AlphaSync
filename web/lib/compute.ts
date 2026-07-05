import type { StrategyBar, ComputedSeries, Stats } from './types'

const BARS_PER_YEAR = 52
const RISK_FREE     = 0.05 / BARS_PER_YEAR

export function computeSeries(
  bars: StrategyBar[],
  initialCapital: number,
  monthlyAdd: number,
): ComputedSeries {
  const n = bars.length
  const dates         = new Array<string>(n)
  const equity        = new Array<number>(n)
  const nav           = new Array<number>(n)
  const spyEquity     = new Array<number>(n)
  const spyNav        = new Array<number>(n)
  const totalInjected = new Array<number>(n)

  let navUnits = initialCapital
  let spyUnits = initialCapital
  let totalInj = 0

  equity[0]        = initialCapital
  if (typeof bars[0].equity === 'number' && Number.isFinite(bars[0].equity)) {
    equity[0] = bars[0].equity
  }
  nav[0] = typeof bars[0].nav === 'number' && Number.isFinite(bars[0].nav) ? bars[0].nav : 1.0
  spyEquity[0]     = initialCapital
  spyNav[0]        = 1.0
  totalInjected[0] = 0
  dates[0]         = bars[0].date

  for (let i = 1; i < n; i++) {
    const bar = bars[i]
    const inj = bar.is_injection ? monthlyAdd : 0

    const navBefore = equity[i - 1] / navUnits
    if (inj > 0) navUnits += inj / navBefore
    const hasRawEquity = typeof bar.equity === 'number' && Number.isFinite(bar.equity)
    const hasRawNav = typeof bar.nav === 'number' && Number.isFinite(bar.nav)
    equity[i] = hasRawEquity ? bar.equity as number : (equity[i - 1] + inj) * (1 + bar.bar_return)
    nav[i]    = hasRawNav ? bar.nav as number : equity[i] / navUnits

    const spyNavBefore = spyEquity[i - 1] / spyUnits
    if (inj > 0) spyUnits += inj / spyNavBefore
    spyEquity[i] = (spyEquity[i - 1] + inj) * (1 + bar.spy_return)
    spyNav[i]    = spyEquity[i] / spyUnits

    totalInj        += inj
    totalInjected[i] = totalInj
    dates[i]         = bar.date
  }

  return { dates, equity, nav, spyEquity, spyNav, totalInjected }
}

function findEndDateIndex(dates: string[], dateStr: string): number {
  for (let i = dates.length - 1; i >= 0; i--) {
    if (dates[i] <= dateStr) return i
  }
  return 0
}

function emptyStats(): Stats {
  return {
    cagr: 0,
    spyCagr: 0,
    alpha: 0,
    mdd: 0,
    sharpe: 0,
    twrCagr: 0,
    twrSpyCagr: 0,
    twrAlpha: 0,
    twrMdd: 0,
    twrSharpe: 0,
    totalInjected: 0,
    netProfit: 0,
    endingEquity: 0,
    endingSpyEquity: 0,
  }
}

function maxDrawdown(values: number[]): number {
  let peak = values[0]
  let mdd = 0
  for (const v of values) {
    if (v > peak) peak = v
    const dd = (v - peak) / peak * 100
    if (dd < mdd) mdd = dd
  }
  return mdd
}

function annualizedSharpe(values: number[]): number {
  const rets: number[] = []
  for (let i = 1; i < values.length; i++) rets.push(values[i] / values[i - 1] - 1)
  if (rets.length === 0) return 0
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length
  const std = Math.sqrt(rets.map(r => (r - mean) ** 2).reduce((a, b) => a + b, 0) / rets.length)
  return std > 0 ? ((mean - RISK_FREE) / std) * Math.sqrt(BARS_PER_YEAR) : 0
}

export function computeStats(series: ComputedSeries, startDate?: string, endDate?: string): Stats {
  const start = startDate ? findDateIndex(series.dates, startDate) : 0
  const end = endDate ? findEndDateIndex(series.dates, endDate) : series.equity.length - 1
  if (end < start) {
    return emptyStats()
  }
  const eq  = series.equity.slice(start, end + 1)
  const spy = series.spyEquity.slice(start, end + 1)
  const nav = series.nav.slice(start, end + 1)
  const spyNav = series.spyNav.slice(start, end + 1)

  if (eq.length < 2) {
    return emptyStats()
  }

  const years = eq.length / BARS_PER_YEAR
  const cagr    = ((eq[eq.length - 1] / eq[0]) ** (1 / years) - 1) * 100
  const spyCagr = ((spy[spy.length - 1] / spy[0]) ** (1 / years) - 1) * 100
  const alpha   = cagr - spyCagr

  const mdd = maxDrawdown(eq)
  const sharpe = annualizedSharpe(eq)
  const twrCagr = ((nav[nav.length - 1] / nav[0]) ** (1 / years) - 1) * 100
  const twrSpyCagr = ((spyNav[spyNav.length - 1] / spyNav[0]) ** (1 / years) - 1) * 100
  const twrAlpha = twrCagr - twrSpyCagr
  const twrMdd = maxDrawdown(nav)
  const twrSharpe = annualizedSharpe(nav)

  const injStart      = series.totalInjected[start]
  const injEnd        = series.totalInjected[end]
  const totalInjected = injEnd - injStart
  const netProfit     = eq[eq.length - 1] - eq[0] - totalInjected

  return {
    cagr,
    spyCagr,
    alpha,
    mdd,
    sharpe,
    twrCagr,
    twrSpyCagr,
    twrAlpha,
    twrMdd,
    twrSharpe,
    totalInjected,
    netProfit,
    endingEquity: eq[eq.length - 1],
    endingSpyEquity: spy[spy.length - 1],
  }
}

export function findDateIndex(dates: string[], dateStr: string): number {
  const idx = dates.findIndex(d => d >= dateStr)
  return idx >= 0 ? idx : 0
}
