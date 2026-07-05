'use client'

import { useEffect, useRef, useState } from 'react'
import type { ComputedSeries, Holding, Trade } from '@/lib/types'

function formatFullDate(date: string) {
  const d = new Date(`${date}T00:00:00`)
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: '2-digit', year: 'numeric' })
}

interface OpenPos {
  ticker: string
  entry_date: string
  entry_price: number
}

interface HoverLabel {
  date: string
  left: number
}

interface Props {
  series: ComputedSeries
  trades: Trade[]
  holdings: Holding[]
  startDate?: string
  endDate?: string
  externalHoverDate?: string | null
  onHover?: (date: string) => void
  onUnhover?: () => void
}

function getRangeBounds(dates: string[], startDate?: string, endDate?: string) {
  let start = 0
  let end = dates.length - 1
  if (startDate) {
    const idx = dates.findIndex((d) => d >= startDate)
    start = idx >= 0 ? idx : 0
  }
  if (endDate) {
    for (let i = dates.length - 1; i >= 0; i--) {
      if (dates[i] <= endDate) {
        end = i
        break
      }
    }
  }
  return { start, end }
}

function getOpenPositions(trades: Trade[], holdings: Holding[], dates: string[], date: string): OpenPos[] {
  const isLatest = date >= dates[dates.length - 1]
  if (isLatest) {
    return holdings.map((h) => ({ ticker: h.ticker, entry_date: h.first_entry_date, entry_price: h.avg_cost }))
  }
  return trades
    .filter((t) => t.entry_date <= date && t.exit_date > date)
    .map((t) => ({ ticker: t.ticker, entry_date: t.entry_date, entry_price: t.entry_price }))
}

function getDateLabelLeft(el: HTMLDivElement, dates: string[], date: string) {
  const idx = dates.findIndex((d) => d === date)
  if (idx < 0) return null
  const width = el.clientWidth
  const plotLeft = 70
  const plotRight = 60
  const plotWidth = Math.max(1, width - plotLeft - plotRight)
  const ratio = dates.length <= 1 ? 0 : idx / (dates.length - 1)
  return Math.min(width - plotRight, Math.max(plotLeft, plotLeft + ratio * plotWidth))
}

async function loadPlotly() {
  const module = await import('plotly.js-dist-min')
  return (module as any).default ?? module
}

const SHARP_BLUE = '#69CCFF'
const GRID_COLOR = 'rgba(124, 144, 170, 0.17)'
const SPY_COLOR = 'rgba(245, 172, 84, 0.84)'

function verticalLineShape(date: string) {
  return {
    type: 'line',
    xref: 'x',
    yref: 'paper',
    x0: date,
    x1: date,
    y0: 0,
    y1: 1,
    line: { color: 'rgba(180,200,255,0.42)', width: 1 },
  }
}

export default function EquityChart({
  series,
  trades,
  holdings,
  startDate,
  endDate,
  externalHoverDate,
  onHover,
  onUnhover,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const suppressRef = useRef(false)
  const hoverDateRef = useRef<string | null>(null)
  const plotReadyRef = useRef(false)
  const [localDate, setLocalDate] = useState<string | null>(null)
  const [openPositions, setOpenPositions] = useState<OpenPos[]>([])
  const [hoverLabel, setHoverLabel] = useState<HoverLabel | null>(null)
  const [plotError, setPlotError] = useState<string | null>(null)
  const [isNarrow, setIsNarrow] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)')
    const update = () => setIsNarrow(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  const setCrosshair = (date: string | null) => {
    if (!ref.current || !plotReadyRef.current) return
    loadPlotly().then((Plotly: any) => {
      if (!ref.current || !plotReadyRef.current) return
      if (!(ref.current as any)._fullLayout) return
      Plotly.relayout(ref.current, { shapes: date ? [verticalLineShape(date)] : [] })
    })
  }

  useEffect(() => {
    let cancelled = false
    if (!ref.current) return

    loadPlotly()
      .then((Plotly: any) => {
        if (cancelled || !ref.current) return
        const { start, end } = getRangeBounds(series.dates, startDate, endDate)
        const dates = series.dates.slice(start, end + 1)
        const equity = series.equity.slice(start, end + 1)
        const spy = series.spyEquity.slice(start, end + 1)
        const traces = [
          {
            x: dates,
            y: equity,
            type: 'scatter',
            mode: 'lines',
            name: 'Strategy',
            line: { color: SHARP_BLUE, width: 1.35 },
            hoverinfo: 'none',
          },
          {
            x: dates,
            y: spy,
            type: 'scatter',
            mode: 'lines',
            name: 'SPY',
            line: { color: SPY_COLOR, width: 1.1, dash: '4px,4px' },
            hoverinfo: 'none',
          },
        ]
        const layout: any = {
          paper_bgcolor: '#1e1e2f',
          plot_bgcolor: '#1e1e2f',
          margin: { t: 10, r: 60, b: 54, l: 70 },
          xaxis: { gridcolor: GRID_COLOR, color: '#78909C', zeroline: false },
          yaxis: { gridcolor: GRID_COLOR, color: '#78909C', tickprefix: '$', zeroline: false },
          showlegend: false,
          hovermode: 'x',
          dragmode: false,
          font: { color: '#90A4AE' },
        }
        const el = ref.current as any
        Plotly.react(el, traces, layout, { displayModeBar: false, responsive: true, scrollZoom: false })
        plotReadyRef.current = true
        el.removeAllListeners?.('plotly_hover')
        el.removeAllListeners?.('plotly_unhover')
        el.on('plotly_hover', (eventData: any) => {
          const pt = eventData?.points?.[0]
          if (!pt) return
          const d = typeof pt.x === 'string' ? pt.x.slice(0, 10) : String(pt.x).slice(0, 10)
          hoverDateRef.current = d
          setLocalDate(d)
          setOpenPositions(getOpenPositions(trades, holdings, series.dates, d))
          const left = getDateLabelLeft(el, dates, d)
          setHoverLabel(left == null ? null : { date: d, left })
          setCrosshair(d)
          suppressRef.current = true
          onHover?.(d)
          setTimeout(() => {
            suppressRef.current = false
          }, 0)
        })
        el.on('plotly_unhover', () => {
          hoverDateRef.current = null
          setLocalDate(null)
          setOpenPositions([])
          setHoverLabel(null)
          setCrosshair(externalHoverDate ?? null)
          onUnhover?.()
        })
        setPlotError(null)
      })
      .catch((error: unknown) => {
        setPlotError(error instanceof Error ? error.message : String(error))
      })

    return () => {
      cancelled = true
    }
  }, [series, startDate, endDate, trades, holdings, onHover, onUnhover])

  useEffect(() => {
    if (!ref.current || suppressRef.current || plotError) return
    if (!externalHoverDate) {
      if (!hoverDateRef.current) setCrosshair(null)
      setHoverLabel(null)
      return
    }
    const { start, end } = getRangeBounds(series.dates, startDate, endDate)
    const dates = series.dates.slice(start, end + 1)
    const left = getDateLabelLeft(ref.current, dates, externalHoverDate)
    setLocalDate(externalHoverDate)
    setOpenPositions(getOpenPositions(trades, holdings, series.dates, externalHoverDate))
    setHoverLabel(left == null ? null : { date: externalHoverDate, left })
    setCrosshair(externalHoverDate)
  }, [externalHoverDate, holdings, plotError, series.dates, startDate, endDate, trades])

  const displayDate = localDate

  const chartHeight = isNarrow ? 300 : 380
  const sideWidth = isNarrow ? 152 : 190

  return (
    <div style={{ display: 'grid', gridTemplateColumns: `minmax(0,1fr) ${sideWidth}px`, gap: 12, alignItems: 'start' }}>
      <div style={{ minWidth: 0, height: chartHeight, position: 'relative' }}>
        <div ref={ref} style={{ width: '100%', height: chartHeight }}>
          {plotError && (
            <div style={{ color: 'var(--red)', padding: 12, fontSize: '0.85em' }}>
              Chart failed: {plotError}
            </div>
          )}
        </div>
        {hoverLabel && (
          <div
            style={{
              position: 'absolute',
              left: hoverLabel.left,
              bottom: 2,
              transform: 'translateX(-50%)',
              color: 'var(--text-muted)',
              background: 'rgba(30,30,47,0.94)',
              border: '1px solid rgba(144,164,174,0.22)',
              borderRadius: 4,
              padding: '2px 6px',
              fontSize: '0.72em',
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
            }}
          >
            {formatFullDate(hoverLabel.date)}
          </div>
        )}
      </div>
      <div
        style={{
          width: sideWidth,
          flexShrink: 0,
          minHeight: chartHeight,
          maxHeight: chartHeight,
          overflowY: 'auto',
          background: 'var(--surface2)',
          borderRadius: 8,
          border: '1px solid var(--border)',
          padding: '10px 12px',
          fontSize: isNarrow ? '0.66em' : '0.72em',
          lineHeight: 1.2,
        }}
      >
        <div style={{ color: 'var(--text-muted)', marginBottom: 6, fontSize: '0.8em', letterSpacing: '.03em' }}>
          {displayDate ?? 'hover chart'}
        </div>
        {openPositions.length === 0 && displayDate && <div style={{ color: 'var(--text-muted)' }}>No open positions</div>}
        {openPositions.map((p) => (
          <div key={p.ticker} style={{ marginBottom: 3 }}>
            <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{p.ticker}</span>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.78em', lineHeight: 1.08 }}>{p.entry_date}</div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.78em', lineHeight: 1.08 }}>${p.entry_price.toFixed(2)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
