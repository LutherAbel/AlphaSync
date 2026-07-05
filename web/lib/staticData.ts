import barsRaw       from '@/data/bars.json'
import holdingsRaw   from '@/data/holdings.json'
import tradesRaw     from '@/data/trades.json'
import executionsRaw from '@/data/executions.json'
import type { StrategyBar, Holding, Trade, Execution } from './types'

export const ALL_BARS:       StrategyBar[] = barsRaw       as StrategyBar[]
export const ALL_HOLDINGS:   Holding[]     = holdingsRaw   as Holding[]
export const ALL_TRADES:     Trade[]       = tradesRaw     as Trade[]
export const ALL_EXECUTIONS: Execution[]   = executionsRaw as Execution[]
