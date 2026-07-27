import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import NoteShell from '@/components/note/NoteShell'
import Fig1 from '@/components/note/Fig1'
import note from '@/data/factor_note.json'
import './note.css'

export const metadata: Metadata = {
  title: 'AlphaSync : Research Notes',
  description:
    'A literature-based momentum implementation with volatility-managed risk control, documented as a public research note.',
}

/** Bilingual inline pair; CSS shows one side based on the shell's data-lang. */
function L({ en, zh }: { en: ReactNode; zh: ReactNode }) {
  return (
    <>
      <span className="en">{en}</span>
      <span className="zh">{zh}</span>
    </>
  )
}

const pct = (v: number, sign = false) =>
  `${sign && v > 0 ? '+' : ''}${parseFloat(v.toFixed(2))}%`
const num = (v: number) => v.toFixed(2)

type RowStats = {
  ann: number
  vol: number
  sharpe: number
  t: number
  skew: number
  worstMonth: number
  maxDD: number
}

export default function ResearchNote() {
  const t1f = note.table1_umd.full as RowStats & { window: string }
  const t1r = note.table1_umd.recent20 as RowStats & { window: string }
  const t4 = note.table4_decomposition
  const t5 = note.table5_crisis
  const hold = note.holdings

  const attribution = note.table3_attribution.map((r) => ({
    ...r,
    label:
      r.series === 'sleeve_plain' ? (
        <L en="AlphaSync sleeve, plain" zh="AlphaSync sleeve,裸版" />
      ) : r.series === 'sleeve_managed' ? (
        <L en="AlphaSync sleeve, managed" zh="AlphaSync sleeve,管理版" />
      ) : (
        r.series
      ),
  }))

  const changelogText: Record<string, { trial: ReactNode; result: ReactNode; decision: ReactNode; cls?: string }> = {
    top20_bsc_value: {
      trial: <L en="Top-20 + BSC + value" zh="Top-20 + BSC + 價值" />,
      result: <L en={`α≈0; crisis ${pct(t5.managed)} vs SPY ${pct(t5.spy)}`} zh={`α≈0;危機月 ${pct(t5.managed)} vs SPY ${pct(t5.spy)}`} />,
      decision: <L en="product core" zh="產品核心" />,
      cls: 'win',
    },
    top10: {
      trial: <L en="Top-10 concentration" zh="Top-10 集中" />,
      result: <L en="Sharpe tie; worse under BSC" zh="Sharpe 打平;BSC 下更差" />,
      decision: <L en="not adopted" zh="不採用" />,
    },
    uncapped_leverage: {
      trial: <L en="Uncapped leverage" zh="無 cap 槓桿" />,
      result: <L en="native max 1.49×; cap ~free" zh="原生上限 1.49×;cap 幾乎免費" />,
      decision: <L en="cap 1.0 kept" zh="保留 cap 1.0" />,
    },
    dm_bear_gate: {
      trial: <L en="DM (2016) bear-state gate" zh="DM(2016)熊市閘門" />,
      result: <L en="whipsaw; all variants < BSC" zh="whipsaw;所有變體 < BSC" />,
      decision: <L en="dropped" zh="剔除" />,
      cls: 'neg',
    },
    residual_momentum: {
      trial: <L en="Residual momentum (2011)" zh="殘差動能(2011)" />,
      result: <L en="corr 0.94; no gain in NDX" zh="相關 0.94;NDX 內無改善" />,
      decision: <L en="dropped (this universe)" zh="剔除(本股池)" />,
      cls: 'neg',
    },
    value_weighted: {
      trial: <L en="Cap-weighted top-20 (SEC shares)" zh="市值加權 top-20(SEC 股數)" />,
      result: <L en="excess over QQQ goes to zero" zh="對 QQQ 超額歸零" />,
      decision: <L en="EW kept; Table 4 recaptioned" zh="維持等權;Table 4 改註" />,
      cls: 'neg',
    },
  }

  return (
    <NoteShell>
      <div className="series">
        <L en="AlphaSync · Research Notes" zh="AlphaSync · 研究筆記" />
        <span className="no">No. 1 · July 2026</span>
      </div>

      <h1>
        <L
          en="A Literature-Based Momentum Implementation, with Volatility-Managed Risk Control"
          zh="一個以文獻為本的動能實作,搭配波動率管理的風控"
        />
      </h1>
      <p className="byline">
        alphasync.capital ·{' '}
        <span className="ver">
          <L en={`Specification ${note.spec}, locked ${note.specLocked}`} zh={`規格 ${note.spec},鎖定於 ${note.specLocked}`} />
        </span>{' '}
        · <a href="#s6"><L en="changelog" zh="變更日誌" /></a>
      </p>

      <section className="abstract">
        <h2><L en="Abstract" zh="摘要" /></h2>
        <p className="en">
          AlphaSync implements published results on a Nasdaq-100 universe: cross-sectional momentum
          (Jegadeesh &amp; Titman 1993) and volatility-managed momentum (Barroso &amp; Santa-Clara 2015).
          The strategy claims no proprietary alpha. The evidence for the premium is the literature, 99
          years of U.S. data and replication across 24 markets, not this backtest. What this page adds is
          an honest account of implementation: what survives dilution to a long-only, no-leverage,
          retail-executable portfolio, and every layer we tested and discarded, documented before you
          invest.
        </p>
        <p className="zh">
          AlphaSync 在 Nasdaq-100 股票池上實作已發表的結果:橫斷面動能(Jegadeesh &amp; Titman 1993)與波動率管理動能(Barroso
          &amp; Santa-Clara 2015)。本策略不宣稱任何自有 alpha。溢酬的證據來自文獻,99 年的美國資料與跨 24
          個市場的複製,不是這份回測。本頁面加上的是一份誠實的實作紀錄:在稀釋成 long-only、無槓桿、散戶可執行的組合後還剩下什麼,以及每一層我們測過又捨棄的東西,都在你投資前先寫清楚。
        </p>
      </section>

      <h2 className="sec">
        <span className="n">1</span>
        <L en="Evidence, in three tiers" zh="三層證據" />
      </h2>
      <p className="en">
        Every number is labeled by its source of evidence. <i>Literature</i>: results established by
        peer-reviewed research on 1927–present data. <i>Replication</i>: those results reproduced
        independently by our pipeline from primary data.<sup><a href="#fn1">1</a></sup>{' '}
        <i>Live record</i>: our own out-of-sample history, which is short, and which we refuse to
        extrapolate from.
      </p>
      <p className="zh">
        每個數字都標注它的證據來源。<i>文獻(Literature)</i>:由同儕審查研究在 1927
        年至今資料上建立的結果。<i>複製(Replication)</i>:那些結果由我們的管線從原始資料獨立重現。
        <sup><a href="#fn1">1</a></sup> <i>實盤紀錄(Live record)</i>:我們自己的樣本外歷史,它很短,而我們拒絕從它外推。
      </p>

      <div className="tbl">
        <table>
          <caption>
            <b>Table 1.</b>{' '}
            <L
              en={
                <>The momentum factor (UMD), Ken French data, monthly. A 20-year window has no statistical power for a Sharpe-0.5 premium; the full-sample <i>t</i> does.</>
              }
              zh={
                <>動能因子(UMD),Ken French 資料,月頻。20 年窗口對 Sharpe 0.5 的溢酬沒有統計檢定力;完整樣本的 <i>t</i> 才有。</>
              }
            />
          </caption>
          <thead>
            <tr>
              <th><L en="Window" zh="窗口" /></th>
              <th><L en="Ann. return" zh="年化報酬" /></th>
              <th>Sharpe</th>
              <th><i>t</i></th>
              <th><L en="Skew" zh="偏度" /></th>
              <th><L en="Worst month" zh="最差月" /></th>
            </tr>
          </thead>
          <tbody>
            {[t1f, t1r].map((r) => (
              <tr key={r.window}>
                <td>{r.window}</td>
                <td>{pct(r.ann, true)}</td>
                <td>{num(r.sharpe)}</td>
                <td>{num(r.t)}</td>
                <td className="neg">{num(r.skew)}</td>
                <td className="neg">{pct(r.worstMonth)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="sec">
        <span className="n">2</span>
        <L en="What risk management can and cannot fix" zh="風控能修什麼、不能修什麼" />
      </h2>
      <p className="en">
        Volatility management repairs momentum&apos;s crash profile; it does not resurrect a dead
        premium. In our replication, the managed variant improves Sharpe by 1.78× in the paper&apos;s own
        sample and by 1.80× in the strictly post-publication window. Every major historical crash is
        attenuated the same way:
      </p>
      <p className="zh">
        波動率管理修的是動能的崩盤形狀,它救不回一個已死的溢酬。在我們的複製裡,管理版在論文自己的樣本內把 Sharpe 改善 1.78
        倍,在嚴格發表後的窗口改善 1.80 倍。每一次重大歷史崩盤都以同樣方式被削弱:
      </p>

      <div className="tbl">
        <table>
          <caption>
            <b>Table 2.</b>{' '}
            <L
              en={<>Momentum crash months, plain vs. managed (our replication, French daily data). Weight shown is the rule&apos;s <i>ex-ante</i> exposure.</>}
              zh={<>動能崩盤月份,裸版 vs 管理版(我們的複製,French 日資料)。權重為規則的<i>事前</i>曝險。</>}
            />
          </caption>
          <thead>
            <tr>
              <th><L en="Month" zh="月份" /></th>
              <th><L en="Plain" zh="裸版" /></th>
              <th><L en="Managed" zh="管理版" /></th>
              <th><L en="Weight" zh="持有權重" /></th>
            </tr>
          </thead>
          <tbody>
            {note.table2_crash.map((r) => (
              <tr key={r.month}>
                <td>{r.month}</td>
                <td className="neg">{pct(r.plain)}</td>
                <td className="neg">{pct(r.managed)}</td>
                <td>{num(r.weight)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <figure>
        <Fig1 />
        <figcaption>
          <b>Figure 1.</b>{' '}
          <L
            en="Cumulative growth (log scale), plain vs. volatility-managed momentum, 1927–2026. Generated from the research pipeline (French daily data); the managed variant scales exposure by inverse realized volatility."
            zh="累積成長(對數座標),裸版 vs 波動率管理動能,1927–2026。由研究管線生成(French 日資料);管理版以實現波動的倒數縮放曝險。"
          />
        </figcaption>
      </figure>

      <h2 className="sec">
        <span className="n">3</span>
        <L en="Attribution: where every basis point comes from" zh="歸因:每一個基點從哪裡來" />
      </h2>
      <p className="en">
        We regress returns on benchmarks you could hold for a few basis points. Whatever the betas absorb
        is not ours. The intercept, with its honest <i>t</i>-statistic, is the only number anyone is
        entitled to call alpha, and on our Nasdaq-100 sleeve it is statistically indistinguishable from
        zero.<sup><a href="#fn2">2</a></sup>
      </p>
      <p className="zh">
        我們把報酬對「你花幾個基點就能持有的基準」做回歸。beta 吸收掉的都不是我們的。截距項,連同它誠實的 <i>t</i>
        值,是唯一有資格被稱為 alpha 的數字,而在我們的 Nasdaq-100 sleeve 上,它與零在統計上無法區分。
        <sup><a href="#fn2">2</a></sup>
      </p>

      <div className="tbl">
        <table>
          <caption>
            <b>Table 3.</b>{' '}
            <L
              en="CAPM attribution, monthly, our pipeline. MTUM shown as the honest yardstick for live long-only momentum."
              zh="CAPM 歸因,月頻,我們的管線。MTUM 作為 live long-only 動能的誠實量尺。"
            />
          </caption>
          <thead>
            <tr>
              <th><L en="Series" zh="序列" /></th>
              <th><L en="vs." zh="對照" /></th>
              <th>β</th>
              <th>α (ann.)</th>
              <th><i>t</i>(α)</th>
            </tr>
          </thead>
          <tbody>
            {attribution.map((r) => (
              <tr key={r.series}>
                <td>{r.label}</td>
                <td>{r.vs}</td>
                <td>{num(r.beta)}</td>
                <td className={r.alpha < 0 ? 'neg' : undefined}>{pct(r.alpha, true)}</td>
                <td className={r.tAlpha < 0 ? 'neg' : undefined}>{num(r.tAlpha)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="en">
        Zero alpha over the index is not the same as zero contribution. Decomposing the sleeve shows
        where the work actually happens: equal-weighting a mega-cap index costs return, and momentum
        selection earns it back. But we also cross-validated the weighting itself (trial #6): a
        cap-weighted variant of the same top-20 shows <i>no</i> excess over QQQ. The selection effect
        below is therefore a property of the equal-weight implementation, a momentum-plus-size-tilt
        composite, not momentum alone.
      </p>
      <p className="zh">
        對指數的 alpha 為零,不等於貢獻為零。把 sleeve
        拆解,可以看到力氣實際上花在哪:等權一個大市值指數會損失報酬,而動能選股把它賺回來。但我們也對加權方式本身做了交叉驗證(試驗
        #6):同一組 top-20 改成市值加權後,對 QQQ <i>沒有</i>任何超額。因此下表的選股效果是等權實作的性質,是「動能 + size
        傾斜」的複合,不是動能單獨的功勞。
      </p>

      <div className="tbl">
        <table>
          <caption>
            <b>Table 4.</b>{' '}
            <L
              en={<>Decomposition, gross, common window. The equal-weight selection effect ({pct(t4.selectionAnn, true)}/yr, <i>t</i> {num(t4.selectionT)}) does not survive cap-weighting: the value-weighted variant&apos;s excess over QQQ is {pct(t4.vwExcessAnn, true)}/yr (<i>t</i> {num(t4.vwExcessT)}). Neither is statistically significant at this sample length.</>}
              zh={<>拆解,毛報酬,共同窗口。等權選股效果({pct(t4.selectionAnn, true)}/年,<i>t</i> {num(t4.selectionT)})未能在市值加權下存活:市值加權版對 QQQ 的超額為 {pct(t4.vwExcessAnn, true)}/年(<i>t</i> {num(t4.vwExcessT)})。在此樣本長度下兩者統計上皆不顯著。</>}
            />
          </caption>
          <thead>
            <tr>
              <th><L en="Portfolio" zh="組合" /></th>
              <th><L en="Ann." zh="年化" /></th>
              <th>Sharpe</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><L en="QQQ (cap-weight NDX)" zh="QQQ(市值加權 NDX)" /></td>
              <td>{pct(t4.qqq.ann)}</td>
              <td>{num(t4.qqq.sharpe)}</td>
            </tr>
            <tr>
              <td><L en="Equal-weight all NDX (no selection)" zh="等權全 NDX(無選股)" /></td>
              <td>{pct(t4.ewNdx.ann)}</td>
              <td>{num(t4.ewNdx.sharpe)}</td>
            </tr>
            <tr>
              <td><L en="Momentum top-20, equal-weight (sleeve)" zh="動能 top-20,等權(sleeve)" /></td>
              <td>{pct(t4.sleeve.ann)}</td>
              <td>{num(t4.sleeve.sharpe)}</td>
            </tr>
            <tr>
              <td><L en="Momentum top-20, cap-weight (trial #6)" zh="動能 top-20,市值加權(試驗 #6)" /></td>
              <td>{pct(t4.vwSleeve.ann)}</td>
              <td>{num(t4.vwSleeve.sharpe)}</td>
            </tr>
            <tr className="rule-top">
              <td><L en="→ selection effect, equal-weight space" zh="→ 選股效果(等權空間)" /></td>
              <td className="win">{pct(t4.selectionAnn, true)}</td>
              <td>{num(t4.selectionSharpe)}</td>
            </tr>
            <tr>
              <td><L en="→ excess over QQQ, cap-weight space" zh="→ 對 QQQ 超額(市值加權空間)" /></td>
              <td className="neg">{pct(t4.vwExcessAnn, true)}</td>
              <td>—</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p className="en">
        The product&apos;s real edge shows up not in average return but in the worst months. Across the
        ten worst months for the S&amp;P 500, the managed sleeve fell less than the index it selects
        from:
      </p>
      <p className="zh">
        產品真正的優勢不在平均報酬,而在最差的月份。在標普 500 最慘的十個月裡,管理版 sleeve 跌得比它選股的指數更少:
      </p>

      <div className="tbl">
        <table>
          <caption>
            <b>Table 5.</b>{' '}
            <L en="Mean return across the 10 worst S&P 500 months, 2015–2026." zh="標普 500 最差 10 個月的平均報酬,2015–2026。" />
          </caption>
          <thead>
            <tr>
              <th>SPY</th>
              <th>QQQ</th>
              <th><L en="Sleeve" zh="sleeve" /></th>
              <th><L en="Managed" zh="管理版" /></th>
              <th><L en="+ Value 50/50" zh="+價值 50/50" /></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="neg">{pct(t5.spy)}</td>
              <td className="neg">{pct(t5.qqq)}</td>
              <td className="neg">{pct(t5.sleeve)}</td>
              <td className="win">{pct(t5.managed)}</td>
              <td>{pct(t5.combo5050)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2 className="sec">
        <span className="n">4</span>
        <L en="Known failure modes" zh="已知失敗模式" />
      </h2>
      <p className="en">
        Momentum&apos;s premium has survived 99 years <i>because</i> it is periodically intolerable: the
        factor spent 2006–2026 statistically flat, and any three-year window can be negative. If you
        enable the optional value sleeve, we disclose up front that value contributed <i>negative</i>{' '}
        returns for the last two decades; its case rests on century-scale and cross-market evidence, not
        recent form. If you cannot hold through that, this product is not for you, and no risk gate we
        ship will change it.
      </p>
      <p className="zh">
        動能的溢酬活了 99 年,<i>正是因為</i>它週期性地令人難以忍受:這個因子在 2006–2026
        統計上趴平,任何三年窗口都可能為負。如果你啟用可選的價值 sleeve,我們事先揭露:價值在過去二十年貢獻為
        <i>負</i>;它的依據是百年尺度與跨市場的證據,不是近期表現。如果你抱不過這個,這個產品不適合你,而我們出的任何風控閘門都改變不了這件事。
      </p>
      <p className="en">
        We also publish what we <i>tried and rejected</i>. Three literature-backed layers were tested on
        this universe and discarded because they did not earn their place, each with its result
        pre-registered before the run:
      </p>
      <p className="zh">
        我們也公開我們<i>測過又否決</i>的東西。三個有文獻背書的層在這個股票池上被測試後捨棄,因為它們沒有掙到自己的位置,每一個的結果都在跑之前就先登記:
      </p>

      <div className="tbl">
        <table>
          <caption>
            <b>Table 6.</b>{' '}
            <L
              en="Change log (excerpt). The full log is public as a commitment device; each trial counts against multiple-testing budget."
              zh="變更日誌(節錄)。完整日誌公開作為一種承諾機制;每次試驗都計入多重檢定預算。"
            />
          </caption>
          <thead>
            <tr>
              <th>#</th>
              <th><L en="Trial" zh="試驗" /></th>
              <th><L en="Result" zh="結果" /></th>
              <th><L en="Decision" zh="決策" /></th>
            </tr>
          </thead>
          <tbody>
            {note.changelog.map((c) => {
              const txt = changelogText[c.trial]
              return (
                <tr key={c.n}>
                  <td>{c.n}</td>
                  <td className="left">{txt.trial}</td>
                  <td className="left">{txt.result}</td>
                  <td className={`left ${txt.cls ?? ''}`}>{txt.decision}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <h2 className="sec">
        <span className="n">5</span>
        <L en="Current portfolio" zh="本月持倉" />
      </h2>
      <p className="note-dim">
        <L
          en={`Top-20 by 12-1 momentum, formation ${hold.month}. Published after execution. Mean one-way turnover ${hold.turnoverMeanPct}%/mo; estimated cost drag ~${hold.costDragBpsYr} bps/yr.`}
          zh={`依 12-1 動能排序的前 20 名,成型月 ${hold.month}。於執行後公布。平均單邊換手率 ${hold.turnoverMeanPct}%/月;估計成本拖累約 ${hold.costDragBpsYr} bps/年。`}
        />
      </p>
      <div className="holdings-grid">
        {hold.tickers.map((tk) => (
          <span key={tk}>{tk}</span>
        ))}
      </div>

      <h2 className="sec" id="s6">
        <span className="n">6</span>
        <L en="Method & changelog" zh="方法與變更日誌" />
      </h2>
      <p className="en">
        The full specification and every change to it are public. Numbers previously published on this
        site (the retired v6 backtest) have been withdrawn; they used a hindsight-selected universe and
        are not interpretable. That correction is itself logged.
      </p>
      <p className="zh">
        完整規格與它的每一次變更都是公開的。本站先前發布的數字(退役的 v6
        回測)已撤下;它們使用了後見之明選出的股票池,無法解讀。這個更正本身也被記錄下來。
      </p>

      <h2 className="sec">
        <L en="References" zh="參考文獻" />
      </h2>
      <ul className="refs">
        <li>Jegadeesh, N., and S. Titman. 1993. &quot;Returns to Buying Winners and Selling Losers.&quot; <i>Journal of Finance</i> 48 (1): 65–91.</li>
        <li>Barroso, P., and P. Santa-Clara. 2015. &quot;Momentum Has Its Moments.&quot; <i>Journal of Financial Economics</i> 116 (1): 111–120.</li>
        <li>Daniel, K., and T. Moskowitz. 2016. &quot;Momentum Crashes.&quot; <i>Journal of Financial Economics</i> 122 (2): 221–247.</li>
        <li>Blitz, D., J. Huij, and M. Martens. 2011. &quot;Residual Momentum.&quot; <i>Journal of Empirical Finance</i> 18 (3): 506–521.</li>
        <li>Bailey, D. H., and M. López de Prado. 2014. &quot;The Deflated Sharpe Ratio.&quot; <i>Journal of Portfolio Management</i> 40 (5): 94–107.</li>
      </ul>

      <div className="fnotes">
        <p id="fn1">
          1.{' '}
          <L
            en={`Pipeline: point-in-time Nasdaq-100 membership; prices include delisted members (${note.coverage.pct}% member-month coverage). Coverage gaps are published, not patched over.`}
            zh={`管線:point-in-time Nasdaq-100 成員資格;價格含已下市成員(成員月覆蓋率 ${note.coverage.pct}%)。覆蓋缺口公開,不做掩蓋。`}
          />
        </p>
        <p id="fn2">
          2.{' '}
          <L
            en="An expected-zero α is not failure. The product is the exposure, the risk control, and this accounting, not a claim to beat the benchmark."
            zh="預期為零的 α 不是失敗。產品是曝險、風控、和這份帳目,不是一個打敗基準的宣稱。"
          />
        </p>
      </div>

    </NoteShell>
  )
}
