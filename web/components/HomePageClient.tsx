'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { User } from '@supabase/supabase-js'
import { ALL_BARS, ALL_EXECUTIONS, ALL_HOLDINGS, ALL_TRADES } from '@/lib/staticData'
import { computeSeries, computeStats } from '@/lib/compute'
import DateRangePicker from '@/components/DateRangePicker'
import EquityChart from '@/components/EquityChart'
import CapitalChart from '@/components/CapitalChart'
import NavChart from '@/components/NavChart'
import HoldingsTable from '@/components/HoldingsTable'
import ExecutionsTable from '@/components/ExecutionsTable'
import type { StrategyBar } from '@/lib/types'
import { createClient } from '@/lib/supabase/client'
import { useUser, type Profile } from '@/lib/useUser'

type HomePageClientProps = {
  initialUser: User | null
  initialProfile: Profile | null
  pageVariant?: 'home' | 'plan'
}

function fmtMoney(n: number) {
  return `$${Math.round(n).toLocaleString('en-US')}`
}

function fmtPct(n: number) {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(1)}%`
}

function fmtDate(date: Date) {
  return date.toISOString().slice(0, 10)
}

function clampDayOfMonth(n: number) {
  if (!Number.isFinite(n)) return 1
  return Math.max(1, Math.min(28, Math.trunc(n)))
}

function formatCadence(bar: StrategyBar | undefined) {
  if (!bar) return '--'
  if (bar.data_frequency === 'daily_7d') return 'Daily K / 7D'
  return bar.data_frequency ?? 'Weekly'
}

export default function HomePageClient({ initialUser, initialProfile, pageVariant = 'home' }: HomePageClientProps) {
  const router = useRouter()
  const pathname = usePathname()
  const isHomePage = pageVariant === 'home'
  const { user, profile } = useUser(initialUser, initialProfile)
  const userMenuRef = useRef<HTMLDivElement | null>(null)
  const [startDate, setStartDate] = useState('2016-01-01')
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [initial, setInitial] = useState(10_000)
  const [monthly, setMonthly] = useState(1_000)
  const [dcaEnabled, setDcaEnabled] = useState(true)
  const [dcaDayOfMonth, setDcaDayOfMonth] = useState(1)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [hoveredDate, setHoveredDate] = useState<string | null>(null)
  const [showUnlockModal, setShowUnlockModal] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  const rangeMinDate = ALL_BARS[0]?.date ?? '2016-01-01'
  const rangeMaxDate = ALL_BARS[ALL_BARS.length - 1]?.date ?? new Date().toISOString().slice(0, 10)
  const latestBar = ALL_BARS[ALL_BARS.length - 1]
  const isSignedIn = !!user
  const isUnlocked = !!(profile?.plan_expires_at && new Date(profile.plan_expires_at) > new Date())
  const supportUsUrl = (
    process.env.NEXT_PUBLIC_SUPPORT_US_URL ??
    process.env.NEXT_PUBLIC_PAYPAL_URL ??
    ''
  ).trim()

  const signIn = async () => {
    const supabase = createClient()
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: typeof window !== 'undefined' ? `${window.location.origin}/auth/callback` : undefined,
      },
    })
  }
  const signOut = async () => {
    const supabase = createClient()
    await supabase.auth.signOut()
  }

  useEffect(() => {
    if (!user) return
    if (profile?.custom_initial != null) setInitial(Number(profile.custom_initial))
    if (profile?.custom_monthly != null) setMonthly(Number(profile.custom_monthly))
    setDcaEnabled(profile?.dca_enabled ?? (Number(profile?.custom_monthly ?? 0) > 0))
    setDcaDayOfMonth(profile?.dca_day_of_month ?? 1)
  }, [user, profile])

  useEffect(() => {
    if (!userMenuOpen) return

    const onClickOutside = (event: MouseEvent) => {
      if (!userMenuRef.current?.contains(event.target as Node)) {
        setUserMenuOpen(false)
      }
    }
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setUserMenuOpen(false)
    }

    window.addEventListener('mousedown', onClickOutside)
    window.addEventListener('keydown', onEscape)
    return () => {
      window.removeEventListener('mousedown', onClickOutside)
      window.removeEventListener('keydown', onEscape)
    }
  }, [userMenuOpen])

  const effectiveMonthly = dcaEnabled ? monthly : 0
  const series = useMemo(() => computeSeries(ALL_BARS, initial, effectiveMonthly), [initial, effectiveMonthly])
  const stats = useMemo(() => computeStats(series, startDate, endDate), [series, startDate, endDate])
  const annualContribution = (dcaEnabled ? monthly : 0) * 12
  const planPreview = useMemo(() => {
    const rows: Array<{ date: string; amount: number; note: string }> = []
    const now = new Date()
    rows.push({
      date: fmtDate(now),
      amount: initial,
      note: 'Initial capital',
    })
    if (!dcaEnabled || monthly <= 0) {
      return rows
    }
    for (let i = 0; i < 6; i++) {
      const dt = new Date(now.getFullYear(), now.getMonth() + i + 1, dcaDayOfMonth)
      rows.push({
        date: fmtDate(dt),
        amount: monthly,
        note: 'Monthly DCA',
      })
    }
    return rows
  }, [initial, dcaEnabled, monthly, dcaDayOfMonth])
  const projectedContribution = useMemo(
    () => planPreview.reduce((sum, row) => sum + row.amount, 0),
    [planPreview],
  )
  const perfSnapshot = useMemo(() => {
    if (series.dates.length === 0) {
      return { date: '--', navChange: 0, nav: 1 }
    }
    const startIdxRaw = series.dates.findIndex((d) => d >= startDate)
    const startIdx = startIdxRaw >= 0 ? startIdxRaw : 0
    let endIdx = series.dates.length - 1
    for (let i = series.dates.length - 1; i >= startIdx; i--) {
      if (series.dates[i] <= endDate) {
        endIdx = i
        break
      }
    }
    const fallbackDate = series.dates[endIdx]
    const effectiveHover = hoveredDate && hoveredDate >= series.dates[startIdx] && hoveredDate <= series.dates[endIdx]
      ? hoveredDate
      : fallbackDate
    const hoverIdx = Math.max(startIdx, series.dates.findIndex((d) => d === effectiveHover))
    const startNav = series.nav[startIdx] ?? 1
    const nav = series.nav[hoverIdx] ?? series.nav[endIdx] ?? 1
    const navChange = startNav !== 0 ? ((nav / startNav) - 1) * 100 : 0
    return {
      date: effectiveHover,
      navChange,
      nav,
    }
  }, [series, startDate, endDate, hoveredDate])

  const saveCapitalPlan = async () => {
    if (!user) return
    const safeInitial = Math.max(1000, Number.isFinite(initial) ? initial : 10_000)
    const safeMonthly = Math.max(0, Number.isFinite(monthly) ? monthly : 0)
    const safeDay = clampDayOfMonth(dcaDayOfMonth)
    setInitial(safeInitial)
    setMonthly(safeMonthly)
    setDcaDayOfMonth(safeDay)
    setSaveState('saving')
    setSaveMessage('')
    const supabase = createClient()
    const { error } = await supabase
      .from('profiles')
      .update({
        custom_initial: safeInitial,
        custom_monthly: safeMonthly,
        dca_enabled: dcaEnabled,
        dca_day_of_month: safeDay,
      })
      .eq('id', user.id)
    if (error) {
      setSaveState('error')
      setSaveMessage(error.message || 'Save failed')
      return
    }
    setSaveState('saved')
    setSaveMessage('Saved')
    setTimeout(() => {
      setSaveState((curr) => (curr === 'saved' ? 'idle' : curr))
      setSaveMessage((curr) => (curr === 'Saved' ? '' : curr))
    }, 1800)
  }

  return (
    <div className="page">
      <header className="as-nav">
        <div className="as-brand">
          <span className="brand-glyph" aria-hidden="true" />
          <span>AlphaSync</span>
        </div>
        <nav className="as-nav-links" aria-label="Primary">
          <Link
            href="/"
            className={pathname === '/' ? 'active' : undefined}
            onClick={(event) => {
              if (pathname === '/') {
                event.preventDefault()
                router.refresh()
              }
            }}
          >
            Homepage
          </Link>
          <Link href="/your-own-plan" className={pathname === '/your-own-plan' ? 'active' : undefined}>
            Your Own Plan
          </Link>
        </nav>
        <div className="as-nav-right">
          {user ? (
            <div className="user-menu" ref={userMenuRef}>
              <button
                className="btn"
                type="button"
                onClick={() => setUserMenuOpen((prev) => !prev)}
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
              >
                {isUnlocked ? 'Subscriber' : 'Signed In'} ▾
              </button>
              {userMenuOpen && (
                <div className="user-menu-dropdown" role="menu">
                  <div className="user-menu-email">{user.email ?? 'User'}</div>
                  {supportUsUrl ? (
                    <a
                      href={supportUsUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="user-menu-item"
                      role="menuitem"
                    >
                      Support Us
                    </a>
                  ) : (
                    <span className="user-menu-item disabled" title="Set NEXT_PUBLIC_SUPPORT_US_URL in your env">
                      Support Us (not configured)
                    </span>
                  )}
                  <button className="user-menu-item" type="button" role="menuitem" onClick={signOut}>
                    Log Out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button className="btn primary" onClick={signIn}>
              Log In / Sign Up
            </button>
          )}
        </div>
      </header>

      {isHomePage && (
      <section className="as-hero" id="hero">
        <div className="hero-inner">
          <div className="eyebrow">Systematic momentum · est. since 2016 backtest</div>
          <h1>
            AlphaSync <span className="muted">Stop trading pennies. Start allocating capital.</span>
          </h1>
          <p className="hero-copy">
            AlphaSync is a systematic momentum engine built from institutional-grade quant models. Regime filters,
            volatility locks, and conviction-weighted sizing - translated into one clear, weekly allocation signal.
          </p>
          <div className="hero-actions">
            <button className="btn primary" onClick={signIn}>
              Access the Engine →
            </button>
            <a className="btn ghost" href="#thesis">View Methodology</a>
          </div>
        </div>
      </section>
      )}

      {isHomePage && (
      <section className="section" id="thesis">
        <div className="section-head">
          <div>
            <div className="section-kicker">01 · The thesis</div>
          </div>
        </div>
        <div className="as-card">
          <div className="thesis-grid">
            <div className="thesis-head">
              <h2>Finding a winner means nothing if you can&apos;t <em>size it</em>.</h2>
            </div>
            <div className="thesis-body">
              <p>
                A 100% return on a timid, fearful position loses to a 10% return on confident core capital every
                time. The bottleneck isn&apos;t stock-picking - it&apos;s <strong>conviction</strong>.
              </p>
              <p>
                AlphaSync solves the conviction problem with institutional regime filters and volatility locks.
                We don&apos;t just surface buy ideas; we provide the structural downside protection required to deploy
                capital at meaningful scale.
              </p>
            </div>
          </div>
          <div className="thesis-vs">
            <div className="bad">
              <div className="tag">Without Architecture</div>
              <h4>Pennies trading</h4>
              <p>Fear-sized positions. Stopped out on noise. Headline-driven exits.</p>
            </div>
            <div className="good">
              <div className="tag">With AlphaSync</div>
              <h4>Capital allocation</h4>
              <p>Regime-filtered exposure. Volatility-scaled sizing. Disciplined deployment.</p>
            </div>
          </div>
        </div>
      </section>
      )}

      {isHomePage && (
      <section className="section" id="architecture">
        <div className="section-head">
          <div>
            <div className="section-kicker">03 · Architecture</div>
            <h2 className="section-title">Risk Architecture</h2>
          </div>
        </div>
        <div className="risk-grid">
          <article className="risk-item">
            <div className="num">01 / REGIME</div>
            <h3>Regime Filter</h3>
            <p>Detects market structure shifts early and suppresses aggressive exposure when trend quality deteriorates.</p>
            <svg className="spark" width="64" height="28" viewBox="0 0 64 28" aria-hidden="true">
              <polyline
                fill="none"
                stroke="var(--mint)"
                strokeWidth="1.2"
                points="0,22 8,18 16,20 24,14 32,16 40,8 48,10 56,5 64,7"
              />
            </svg>
          </article>
          <article className="risk-item">
            <div className="num">02 / VOL</div>
            <h3>Volatility Locks</h3>
            <p>Volatility-aware guardrails cut tail risk and prevent emotional overreaction in shock periods.</p>
            <svg className="spark" width="64" height="28" viewBox="0 0 64 28" aria-hidden="true">
              <polyline
                fill="none"
                stroke="var(--amber)"
                strokeWidth="1.2"
                points="0,14 8,8 16,18 24,6 32,20 40,10 48,16 56,12 64,14"
              />
            </svg>
          </article>
          <article className="risk-item">
            <div className="num">03 / CONVICTION</div>
            <h3>Conviction Allocation</h3>
            <p>Strategy confidence is translated directly into position size. Core capital deploys with mathematical discipline.</p>
            <svg className="spark" width="64" height="28" viewBox="0 0 64 28" aria-hidden="true">
              <rect x="2" y="16" width="6" height="10" fill="var(--mint-dim)" />
              <rect x="12" y="10" width="6" height="16" fill="var(--mint-dim)" />
              <rect x="22" y="14" width="6" height="12" fill="var(--mint-dim)" />
              <rect x="32" y="4" width="6" height="22" fill="var(--mint)" />
              <rect x="42" y="12" width="6" height="14" fill="var(--mint-dim)" />
              <rect x="52" y="6" width="6" height="20" fill="var(--mint)" />
            </svg>
          </article>
        </div>
      </section>
      )}

      <section className="section" id="performance">
        {!isHomePage && (
          <div className="section-head">
            <div>
              <div className="section-kicker">Plan · Projection</div>
              <h2 className="section-title">Your Own Plan</h2>
              <p className="section-sub">This projection is computed from your saved capital setup, so cloud deploy will read the same user plan.</p>
            </div>
          </div>
        )}
        {isHomePage && (
          <div className="section-head">
            <div>
              <div className="section-kicker">04 · Performance</div>
              <h2 className="section-title">Strategy vs SPY</h2>
              <p className="section-sub">Historical capital curve, drawdown-aware stats, and synchronized benchmark comparison.</p>
            </div>
          </div>
        )}
        <div className="as-card">
          {user && (
            <div className="capital-plan">
              <div className="capital-plan-head">
                <div>
                  <div className="card-label">Capital Setup</div>
                  <div className="capital-plan-title">Initial capital and DCA cadence</div>
                </div>
                <button className="btn" onClick={saveCapitalPlan} disabled={saveState === 'saving'}>
                  {saveState === 'saving' ? 'Saving...' : 'Save Plan'}
                </button>
              </div>
              <div className="capital-plan-grid">
                <label>
                  Initial Capital
                  <input
                    type="number"
                    min={1000}
                    step={1000}
                    value={initial}
                    onChange={(e) => setInitial(Number(e.target.value))}
                  />
                </label>
                <label>
                  Monthly DCA Amount
                  <input
                    type="number"
                    min={0}
                    step={100}
                    value={monthly}
                    disabled={!dcaEnabled}
                    onChange={(e) => setMonthly(Number(e.target.value))}
                  />
                </label>
                <label>
                  Injection Day (monthly)
                  <input
                    type="number"
                    min={1}
                    max={28}
                    value={dcaDayOfMonth}
                    disabled={!dcaEnabled}
                    onChange={(e) => setDcaDayOfMonth(clampDayOfMonth(Number(e.target.value)))}
                  />
                </label>
              </div>
              <div className="capital-plan-row">
                <label className="capital-toggle">
                  <input
                    type="checkbox"
                    checked={dcaEnabled}
                    onChange={(e) => setDcaEnabled(e.target.checked)}
                  />
                  Enable DCA
                </label>
                <div className="capital-summary">
                  Annual planned contribution: {fmtMoney(annualContribution)}
                </div>
                {saveMessage && (
                  <div className={`capital-save-msg ${saveState === 'error' ? 'error' : 'ok'}`}>{saveMessage}</div>
                )}
              </div>
            </div>
          )}
          {!isHomePage && user && (
            <div className="plan-preview">
              <div className="plan-preview-head">
                <span className="card-label">Computed from your settings</span>
                <span className="plan-preview-total">Projected next injections: {fmtMoney(projectedContribution)}</span>
              </div>
              <div className="plan-preview-list">
                {planPreview.map((row) => (
                  <div key={`${row.date}-${row.note}`} className="plan-preview-row">
                    <span>{row.date}</span>
                    <span>{row.note}</span>
                    <strong>{fmtMoney(row.amount)}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="card-head">
            <div className="card-title-row">
              <span className="card-label">Range & Inputs</span>
            </div>
            <div className="chart-toolbar">
              <DateRangePicker
                startDate={startDate}
                endDate={endDate}
                minDate={rangeMinDate}
                maxDate={rangeMaxDate}
                onChange={(s, e) => {
                  setStartDate(s)
                  setEndDate(e)
                }}
              />
              {isUnlocked && (
                <>
                  <label className="input-inline">
                    Initial
                    <input type="number" value={initial} step={1000} min={1000} onChange={(e) => setInitial(Number(e.target.value))} />
                  </label>
                  <label className="input-inline">
                    Monthly
                    <input type="number" value={monthly} step={100} min={0} onChange={(e) => setMonthly(Number(e.target.value))} />
                  </label>
                </>
              )}
            </div>
          </div>

          <div className="perf-stats">
            <div className="perf-stat-card">
              <div className="label">CAGR</div>
              <div className={`value ${stats.cagr >= 0 ? 'pos' : 'neg'}`}>{fmtPct(stats.cagr)}</div>
              <div className="delta">Annualized to hover date</div>
            </div>
            <div className="perf-stat-card">
              <div className="label">Alpha vs SPY</div>
              <div className={`value ${stats.alpha >= 0 ? 'pos' : 'neg'}`}>{fmtPct(stats.alpha)}</div>
              <div className="delta">Annualized excess</div>
            </div>
            <div className="perf-stat-card">
              <div className="label">Max Drawdown</div>
              <div className="value neg">{stats.mdd.toFixed(1)}%</div>
              <div className="delta">Lower is better</div>
            </div>
            <div className="perf-stat-card">
              <div className="label">Net Profit</div>
              <div className={`value ${stats.netProfit >= 0 ? 'pos' : 'neg'}`}>{fmtMoney(stats.netProfit)}</div>
              <div className="delta">After injections</div>
            </div>
          </div>
          <div className="perf-stats-strip">
            <span className="strip-key">HOVER</span>
            <span>{perfSnapshot.date} · LIVE</span>
            <span className="strip-key">NAV CHANGE</span>
            <span className={perfSnapshot.navChange >= 0 ? 'pos' : 'neg'}>{fmtPct(perfSnapshot.navChange)}</span>
            <span className="strip-key">NAV</span>
            <span>{perfSnapshot.nav.toFixed(3)}</span>
          </div>

          <div className="legend">
            <span className="sw"><span className="swatch" /> Strategy</span>
            <span className="sw"><span className="swatch benchmark" /> SPY</span>
          </div>

          <div className="perf-row" style={{ marginBottom: 14 }}>
            <div className="chart-box">
              <EquityChart
                series={series}
                trades={ALL_TRADES}
                holdings={ALL_HOLDINGS}
                startDate={startDate}
                endDate={endDate}
                externalHoverDate={hoveredDate}
                onHover={setHoveredDate}
                onUnhover={() => setHoveredDate(null)}
              />
            </div>
          </div>

          <div style={{ marginTop: 26, paddingTop: 16, borderTop: '1px solid var(--bd-1)' }}>
            <div className="card-head" style={{ marginBottom: 8 }}>
              <div className="card-title-row">
                <span className="card-label">Capital Allocation · Regime</span>
              </div>
            </div>
            <CapitalChart
              bars={ALL_BARS}
              startDate={startDate}
              endDate={endDate}
              externalHoverDate={hoveredDate}
              onHover={setHoveredDate}
              onUnhover={() => setHoveredDate(null)}
              height={220}
            />
          </div>

          <div style={{ marginTop: 26, paddingTop: 16, borderTop: '1px solid var(--bd-1)' }}>
            <div className="card-head" style={{ marginBottom: 8 }}>
              <div className="card-title-row">
                <span className="card-label">NAV Trajectory</span>
              </div>
            </div>
            <NavChart
              series={series}
              startDate={startDate}
              endDate={endDate}
            />
          </div>
        </div>
      </section>

      <section className="section" id="signals">
        <div className="as-card">
          <div className="card-head">
            <div className="card-title-row">
              <span className="card-label">05 · Current signals</span>
            </div>
            {!isSignedIn && (
              <button className="btn" onClick={() => setShowUnlockModal(true)}>
                Sign In
              </button>
            )}
          </div>

          <HoldingsTable
            holdings={ALL_HOLDINGS}
            locked={!isSignedIn}
            onRequestUnlock={() => setShowUnlockModal(true)}
          />
        </div>
      </section>

      <section className="section" id="log">
        <div className="as-card">
          <div className="card-head">
            <div className="card-title-row">
              <span className="card-label">06 · Execution log</span>
            </div>
          </div>
          <ExecutionsTable
            executions={ALL_EXECUTIONS}
            bars={ALL_BARS}
            startDate={startDate}
            endDate={endDate}
          />
        </div>
      </section>

      <footer className="footer">
        <div className="fcol fmark">
          <div className="as-brand" style={{ marginBottom: 4 }}>
            <span className="brand-glyph" aria-hidden="true" />
            <span>AlphaSync</span>
          </div>
          <p>Upside by momentum. Downside by math. Systematic allocation signals for long-horizon capital.</p>
        </div>
        <div className="fcol">
          <h5>Company</h5>
          <a href="#">About</a>
          <a href="#">Research</a>
          <a href="#">Contact</a>
        </div>
        <div className="fcol">
          <h5>Legal</h5>
          <a href="#">Terms</a>
          <a href="#">Privacy</a>
          <a href="#">Disclaimer</a>
        </div>
        <div className="fdisclaimer">
          NOT INVESTMENT ADVICE. AlphaSync publishes systematic model output for informational purposes only.
          Past performance, including backtested results, does not guarantee future results.
        </div>
      </footer>

      {showUnlockModal && (
        <div className="unlock-modal-backdrop" onClick={() => setShowUnlockModal(false)}>
          <div className="unlock-modal" onClick={(e) => e.stopPropagation()}>
            <div className="unlock-modal-title">解鎖完整持倉與同步配置</div>
            <p>註冊後可查看完整持倉、目標權重與同步金額。</p>
            <div className="unlock-modal-actions">
              <button className="btn primary" onClick={signIn}>
                註冊並解鎖
              </button>
              <button className="btn" onClick={() => setShowUnlockModal(false)}>
                稍後再說
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
