import note from '@/data/factor_note.json'

/** Figure 1: real cumulative log10 equity, plain vs vol-managed UMD, 1927-2026.
 *  Server-rendered SVG from pipeline data; no client JS. */
export default function Fig1() {
  const { months, plainLog10, managedLog10 } = note.fig1
  const W = 1440
  const H = 620
  const L = 78
  const R = 30
  const T = 20
  const B = 46

  const all = [...plainLog10, ...managedLog10]
  const ymin = Math.min(...all) - 0.2
  const ymax = Math.max(...all) + 0.3
  const X = (i: number) => L + ((W - L - R) * i) / (months.length - 1)
  const Y = (v: number) => T + (H - T - B) * (1 - (v - ymin) / (ymax - ymin))

  const path = (data: number[]) =>
    data.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join('')

  const gridVals = [0, 2, 4, 6].filter((g) => g >= ymin && g <= ymax)
  const decades = ['1927', '1950', '1975', '2000', '2026']
  const decadeIdx = decades.map((d) =>
    Math.max(0, months.findIndex((m: string) => m.startsWith(d)))
  )
  decadeIdx[decadeIdx.length - 1] = months.length - 1

  const lastP = plainLog10[plainLog10.length - 1]
  const lastM = managedLog10[managedLog10.length - 1]

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cumulative growth, plain vs managed momentum">
      <rect width={W} height={H} fill="#FCFCF8" />
      {gridVals.map((g) => (
        <g key={g}>
          <line x1={L} x2={W - R} y1={Y(g)} y2={Y(g)} stroke="#E4E1D6" strokeWidth={1} />
          <text x={L - 10} y={Y(g) + 7} textAnchor="end" fontSize={22} fontFamily="Georgia, serif" fill="#6E6A60">
            {g === 0 ? '$1' : `$10${g === 2 ? '²' : g === 4 ? '⁴' : '⁶'}`}
          </text>
        </g>
      ))}
      {decades.map((d, i) => (
        <text key={d} x={X(decadeIdx[i])} y={H - 14} textAnchor="middle" fontSize={22} fontFamily="Georgia, serif" fill="#6E6A60">
          {d}
        </text>
      ))}
      <path d={path(plainLog10)} fill="none" stroke="#8A857A" strokeWidth={2.5} />
      <path d={path(managedLog10)} fill="none" stroke="#2E5680" strokeWidth={3} />
      <text x={W - R - 8} y={Y(lastM) - 12} textAnchor="end" fontSize={23} fontFamily="Georgia, serif" fill="#2E5680">
        managed
      </text>
      <text x={W - R - 8} y={Y(lastP) + 30} textAnchor="end" fontSize={23} fontFamily="Georgia, serif" fill="#8A857A">
        plain
      </text>
    </svg>
  )
}
