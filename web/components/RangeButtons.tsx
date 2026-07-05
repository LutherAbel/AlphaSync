'use client'
import { useState } from 'react'

const RANGES = [
  { label: 'All',   start: '2016-01-01' },
  { label: '2018+', start: '2018-01-01' },
  { label: '2020+', start: '2020-01-01' },
  { label: '2022+', start: '2022-01-01' },
  { label: '2023+', start: '2023-01-01' },
  { label: '2024+', start: '2024-01-01' },
  { label: '2025+', start: '2025-01-01' },
  { label: 'YTD',   start: `${new Date().getFullYear()}-01-01` },
  { label: '1Y',    start: (() => { const d = new Date(); d.setFullYear(d.getFullYear() - 1); return d.toISOString().slice(0, 10) })() },
]

interface Props {
  onChange: (startDate: string) => void
}

export default function RangeButtons({ onChange }: Props) {
  const [active, setActive] = useState('All')

  function handleClick(label: string, start: string) {
    setActive(label)
    onChange(start)
  }

  return (
    <div className="tog-group">
      {RANGES.map(({ label, start }) => (
        <button
          key={label}
          className={`tog-btn${active === label ? ' active' : ''}`}
          onClick={() => handleClick(label, start)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
