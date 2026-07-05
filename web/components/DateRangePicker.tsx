'use client'

interface Props {
  startDate: string   // 'YYYY-MM-DD'
  endDate: string     // 'YYYY-MM-DD'
  minDate: string     // earliest available data date
  maxDate: string     // latest available data date
  onChange: (start: string, end: string) => void
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.82em', color: 'var(--text-muted)',
}

const inputStyle: React.CSSProperties = {
  background: 'var(--surface2)', border: '1px solid var(--border2)',
  borderRadius: 6, color: 'var(--text)', padding: '4px 8px',
  fontSize: '0.82em', colorScheme: 'dark',
}

export default function DateRangePicker({ startDate, endDate, minDate, maxDate, onChange }: Props) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={labelStyle}>From</span>
      <input
        type="date"
        value={startDate}
        min={minDate}
        max={endDate}
        style={inputStyle}
        onChange={e => {
          const v = e.target.value
          if (v && v <= endDate) onChange(v, endDate)
        }}
      />
      <span style={labelStyle}>To</span>
      <input
        type="date"
        value={endDate}
        min={startDate}
        max={maxDate}
        style={inputStyle}
        onChange={e => {
          const v = e.target.value
          if (v && v >= startDate) onChange(startDate, v)
        }}
      />
    </div>
  )
}
