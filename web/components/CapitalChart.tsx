'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { StrategyBar } from '@/lib/types'

function formatFullDate(date: string) {
  const d = new Date(`${date}T00:00:00`)
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: '2-digit', year: 'numeric' })
}

interface Props {
  bars: StrategyBar[]
  startDate?: string
  endDate?: string
  externalHoverDate?: string | null
  onHover?: (date: string) => void
  onUnhover?: () => void
  height?: number
}

interface HoverLabel {
  date: string
  left: number
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

function getRegimeLabel(score: number) {
  if (score >= 0.5) return 'Risk-on'
  if (score < -0.5) return 'Deep stress'
  if (score < 0.1) return 'Risk-off'
  return 'Neutral'
}

function getExposureLabel(longPct: number) {
  if (longPct >= 95) return 'Full exposure'
  if (longPct <= 5) return 'Cash mode'
  return 'Partial exposure'
}

function findBarByDate(bars: StrategyBar[], date: string | null | undefined) {
  if (!date) return null
  return bars.find((bar) => bar.date === date) ?? null
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

export default function CapitalChart({ bars, startDate, endDate, externalHoverDate, onHover, onUnhover, height = 260 }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const plotReadyRef = useRef(false)
  const suppressRef = useRef(false)
  const hoverDateRef = useRef<string | null>(null)
  const [activeBar, setActiveBar] = useState<StrategyBar | null>(null)
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

  const visibleBars = useMemo(() => {
    const { start, end } = getRangeBounds(bars.map((b) => b.date), startDate, endDate)
    return bars.slice(start, end + 1)
  }, [bars, startDate, endDate])
  const displayBar = activeBar ?? visibleBars[visibleBars.length - 1] ?? null

  useEffect(() => {
    let cancelled = false
    if (!ref.current) return
    loadPlotly()
      .then((Plotly: any) => {
        if (cancelled || !ref.current) return
        const { start, end } = getRangeBounds(bars.map((b) => b.date), startDate, endDate)
        const slice = bars.slice(start, end + 1)
        const dates = slice.map((b) => b.date)
        const longs = slice.map((b) => b.long_pct)
        const regime = slice.map((b) => b.regime_score ?? null)
        const traces = [
          {
            x: dates,
            y: longs,
            type: 'scatter',
            mode: 'lines',
            name: 'Long %',
            line: { color: SHARP_BLUE, width: 1.35 },
            yaxis: 'y',
            hoverinfo: 'none',
          },
          {
            x: dates,
            y: regime,
            type: 'scatter',
            mode: 'lines',
            name: 'Regime',
            line: { color: 'rgba(255,213,79,0.72)', width: 1.1, dash: '4px,4px' },
            yaxis: 'y2',
            hoverinfo: 'none',
          },
        ]
        const layout: any = {
          paper_bgcolor: '#1e1e2f',
          plot_bgcolor: '#1e1e2f',
          margin: { t: 10, r: 60, b: 54, l: 70 },
          xaxis: { gridcolor: GRID_COLOR, color: '#78909C', zeroline: false },
          yaxis: {
            gridcolor: GRID_COLOR,
            color: '#78909C',
            ticksuffix: '%',
            range: [0, 105],
            zeroline: false,
            title: { text: 'Long %', font: { color: '#78909C', size: 11 } },
          },
          yaxis2: {
            overlaying: 'y',
            side: 'right',
            color: 'rgba(255,213,79,0.6)',
            gridcolor: 'transparent',
            range: [-1.1, 1.1],
            tickformat: '.1f',
            title: { text: 'Regime', font: { color: 'rgba(255,213,79,0.6)', size: 11 } },
          },
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
          setActiveBar(findBarByDate(bars, d))
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
          setActiveBar(null)
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
  }, [bars, startDate, endDate, onHover, onUnhover])

  useEffect(() => {
    if (!ref.current || suppressRef.current || plotError) return
    if (!externalHoverDate) {
      setActiveBar(null)
      setHoverLabel(null)
      if (!hoverDateRef.current) setCrosshair(null)
      return
    }
    const { start, end } = getRangeBounds(bars.map((b) => b.date), startDate, endDate)
    const dates = bars.slice(start, end + 1).map((b) => b.date)
    const left = getDateLabelLeft(ref.current, dates, externalHoverDate)
    setActiveBar(findBarByDate(bars, externalHoverDate))
    setHoverLabel(left == null ? null : { date: externalHoverDate, left })
    setCrosshair(externalHoverDate)
  }, [bars, externalHoverDate, plotError, startDate, endDate])

  const chartHeight = isNarrow ? Math.max(200, height - 36) : height
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
          fontSize: isNarrow ? '0.72em' : '0.78em',
          lineHeight: 1.2,
        }}
      >
        <div style={{ color: 'var(--text-muted)', marginBottom: 8, fontSize: '0.85em', letterSpacing: '.04em' }}>
          {displayBar ? `${displayBar.signal_date ?? displayBar.date} → ${displayBar.execution_date ?? displayBar.date}` : 'exposure'}
        </div>
        {displayBar ? (
          <>
            <div style={{ color: displayBar.long_pct <= 5 ? 'var(--red)' : 'var(--accent)', fontSize: '1.55em', fontWeight: 700 }}>
              {displayBar.long_pct.toFixed(1)}%
            </div>
            <div style={{ color: 'var(--text-muted)', marginBottom: 10 }}>{getExposureLabel(displayBar.long_pct)}</div>
            <div style={{ display: 'grid', gap: 6 }}>
              <div>
                <div style={{ color: 'var(--text-dim)' }}>Regime</div>
                <div style={{ color: displayBar.regime_score < 0.1 ? '#FFD54F' : 'var(--text)' }}>
                  {displayBar.regime_score.toFixed(3)} · {getRegimeLabel(displayBar.regime_score)}
                </div>
              </div>
              <div>
                <div style={{ color: 'var(--text-dim)' }}>Holdings</div>
                <div style={{ color: 'var(--text)' }}>{displayBar.long_n}</div>
              </div>
              <div>
                <div style={{ color: 'var(--text-dim)' }}>CS Stage</div>
                <div style={{ color: 'var(--text)' }}>{displayBar.cs_stage || '-'}</div>
              </div>
            </div>
          </>
        ) : (
          <div style={{ color: 'var(--text-muted)' }}>Hover chart to inspect exposure.</div>
        )}
      </div>
    </div>
  )
}
