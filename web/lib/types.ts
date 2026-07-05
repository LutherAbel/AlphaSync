export interface StrategyBar {
  date: string
  signal_date?: string
  execution_date?: string
  data_frequency?: string
  equity?: number
  nav?: number
  bar_return: number
  is_injection: boolean
  spy_return: number
  dual_gate?: boolean
  regime_score: number
  long_pct: number
  long_n: number
  cs_stage: string
  total_injected: number
}

export interface Holding {
  ticker: string
  first_entry_date: string
  avg_cost: number
  current_price: number
  position_value: number
  weight: number
  shares: number
  sleeve: string
}

export interface Trade {
  ticker: string
  entry_date: string
  exit_date: string
  entry_price: number
  exit_price: number
  shares: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  hold_bars: number
}

export interface Execution {
  date: string
  ticker: string
  action: 'BUY' | 'ADD' | 'SELL' | 'REDUCE'
  shares: number
  price: number
  avg_price_before: number | null
  sleeve: string
  reason: string
  pnl_pct: number | null
  pnl_dollar: number | null
}

export interface ComputedSeries {
  dates: string[]
  equity: number[]
  nav: number[]
  spyEquity: number[]
  spyNav: number[]
  totalInjected: number[]
}

export interface Stats {
  cagr: number
  spyCagr: number
  alpha: number
  mdd: number
  sharpe: number
  twrCagr: number
  twrSpyCagr: number
  twrAlpha: number
  twrMdd: number
  twrSharpe: number
  totalInjected: number
  netProfit: number
  endingEquity: number
  endingSpyEquity: number
}
