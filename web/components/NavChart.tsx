'use client'

import { useEffect, useRef, useState } from 'react'
import type { ComputedSeries } from '@/lib/types'

interface Props {
  series: ComputedSeries
  startDate?: string
  endDate?: string
}

interface NavPoint {
  date: string
  nav: number
  spyNav: number
}

const CROSSHAIR_SHAPE = (x: string) => ({
  type: 'line',
  xref: 'x',
  yref: 'paper',
  x0: x,
  x1: x,
  y0: 0,
  y1: 1,
  line: { color: 'rgba(180,200,255,0.38)', width: 1 },
})

const ANCHOR_SHAPE = (x: string) => ({
  type: 'line',
  xref: 'x',
  yref: 'paper',
  x0: x,
  x1: x,
  y0: 0,
  y1: 1,
  line: { color: 'rgba(255,213,79,0.72)', width: 1.5, dash: 'dot' },
})

function formatMonthYear(date: string) {
  const d = new Date(`${date}T00:00:00`)
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
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

interface HoverLabel {
  date: string
  left: number
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

export default function NavChart({ series, startDate, endDate }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<NavPoint | null>(null)
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

  useEffect(() => {
    setAnchor(null)
  }, [startDate, endDate])

  useEffect(() => {
    let cancelled = false
    if (!ref.current) return

    loadPlotly()
      .then((Plotly: any) => {
        if (cancelled || !ref.current) return
        const { start, end } = getRangeBounds(series.dates, startDate, endDate)
        const dates = series.dates.slice(start, end + 1)
        const nav = series.nav.slice(start, end + 1)
        const spyNav = series.spyNav.slice(start, end + 1)

        const traces = [
          {
            x: dates,
            y: nav,
            type: 'scatter',
            mode: 'lines',
            name: 'Strategy NAV',
            line: { color: SHARP_BLUE, width: 1.35 },
            fill: 'tozeroy',
            fillcolor: 'rgba(105,204,255,0.02)',
            hoverinfo: 'none',
          },
          {
            x: dates,
            y: spyNav,
            type: 'scatter',
            mode: 'lines',
            name: 'SPY NAV',
            line: { color: SPY_COLOR, width: 1.1, dash: '4px,4px' },
            hoverinfo: 'none',
          },
        ]

        const layout: any = {
          paper_bgcolor: '#1e1e2f',
          plot_bgcolor: '#1e1e2f',
          margin: { t: 10, r: 60, b: 54, l: 70 },
          xaxis: { gridcolor: GRID_COLOR, color: '#78909C', zeroline: false },
          yaxis: { gridcolor: GRID_COLOR, color: '#78909C', zeroline: false },
          showlegend: false,
          hovermode: 'x',
          dragmode: false,
          font: { color: '#90A4AE' },
          shapes: anchor ? [ANCHOR_SHAPE(anchor.date)] : [],
        }

        const el = ref.current as any
        const updateHover = (date: string) => {
          const left = getDateLabelLeft(el, dates, date)
          setHoverLabel(left == null ? null : { date, left })
        }

        Plotly.react(el, traces, layout, { displayModeBar: false, responsive: true, scrollZoom: false })
        el.removeAllListeners?.('plotly_hover')
        el.removeAllListeners?.('plotly_unhover')
        el.removeAllListeners?.('plotly_click')
        el.removeAllListeners?.('plotly_doubleclick')
        el.on('plotly_hover', (eventData: any) => {
          const pt = eventData?.points?.[0]
          if (!pt) return
          const d = typeof pt.x === 'string' ? pt.x.slice(0, 10) : String(pt.x).slice(0, 10)
          updateHover(d)
        })
        el.on('plotly_unhover', () => {
          setHoverLabel(null)
        })
        el.on('plotly_click', (eventData: any) => {
          const pt = eventData?.points?.find((p: any) => p.curveNumber === 0) ?? eventData?.points?.[0]
          if (!pt) return
          const d = typeof pt.x === 'string' ? pt.x.slice(0, 10) : String(pt.x).slice(0, 10)
          const idx = dates.findIndex((date) => date === d)
          if (idx < 0) return
          setAnchor({ date: d, nav: nav[idx], spyNav: spyNav[idx] })
        })
        el.on('plotly_doubleclick', () => {
          setAnchor(null)
          setHoverLabel(null)
        })
        setPlotError(null)
      })
      .catch((error: unknown) => {
        setPlotError(error instanceof Error ? error.message : String(error))
      })

    return () => {
      cancelled = true
    }
  }, [series, startDate, endDate, anchor])

  const chartHeight = isNarrow ? 300 : 340
  const sideWidth = isNarrow ? 152 : 190

  return (
    <div style={{ display: 'grid', gridTemplateColumns: `minmax(0,1fr) ${sideWidth}px`, gap: 12, alignItems: 'start', marginTop: 12 }}>
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
            {formatMonthYear(hoverLabel.date)}
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
          fontSize: '0.78em',
        }}
      >
        <div style={{ color: 'var(--text-muted)', marginBottom: 8, fontSize: '0.85em', letterSpacing: '.04em' }}>
          Ticker
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: SHARP_BLUE }} />
            <span>Strategy</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: SPY_COLOR }} />
            <span>SPY</span>
          </div>
        </div>
      </div>
    </div>
  )
}
