"""Generate the static research-note site from web/data/factor_note.json.

Replaces the Next.js build: outputs a single self-contained site/index.html
(inline CSS + inline SVG + a few lines of vanilla JS for the EN/中文 toggle).
Content mirrors the note as deployed 2026-08 (no stamp, no footer).
"""

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(ROOT, "..")
NOTE = os.path.join(REPO, "web", "data", "factor_note.json")
SITE = os.path.join(REPO, "site")
CSS = os.path.join(REPO, "web", "app", "note.css")


def pct(v, sign=False):
    s = "+" if (sign and v > 0) else ""
    return f"{s}{round(v + 0.0, 2):g}%"


def num(v):
    return f"{v:.2f}"


def L(en, zh):
    return f'<span class="en">{en}</span><span class="zh">{zh}</span>'


def fig1_svg(fig):
    months, plain, managed = fig["months"], fig["plainLog10"], fig["managedLog10"]
    W, H, Lm, R, T, B = 1440, 620, 78, 30, 20, 46
    allv = plain + managed
    ymin, ymax = min(allv) - 0.2, max(allv) + 0.3
    n = len(months)
    X = lambda i: Lm + (W - Lm - R) * i / (n - 1)
    Y = lambda v: T + (H - T - B) * (1 - (v - ymin) / (ymax - ymin))
    path = lambda d: "".join(f"{'L' if i else 'M'}{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(d))
    grid = ""
    for g in (0, 2, 4, 6):
        if ymin <= g <= ymax:
            lab = "$1" if g == 0 else f"$10{'²' if g == 2 else '⁴' if g == 4 else '⁶'}"
            grid += (f'<line x1="{Lm}" x2="{W-R}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" stroke="#E4E1D6"/>'
                     f'<text x="{Lm-10}" y="{Y(g)+7:.1f}" text-anchor="end" font-size="22" '
                     f'font-family="Georgia,serif" fill="#6E6A60">{lab}</text>')
    decades = ["1927", "1950", "1975", "2000", "2026"]
    idx = [next((i for i, m in enumerate(months) if m.startswith(d)), 0) for d in decades]
    idx[-1] = n - 1
    xlab = "".join(f'<text x="{X(i):.1f}" y="{H-14}" text-anchor="middle" font-size="22" '
                   f'font-family="Georgia,serif" fill="#6E6A60">{d}</text>' for d, i in zip(decades, idx))
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Cumulative growth, plain vs managed momentum">'
            f'<rect width="{W}" height="{H}" fill="#FCFCF8"/>{grid}{xlab}'
            f'<path d="{path(plain)}" fill="none" stroke="#8A857A" stroke-width="2.5"/>'
            f'<path d="{path(managed)}" fill="none" stroke="#2E5680" stroke-width="3"/>'
            f'<text x="{W-R-8}" y="{Y(managed[-1])-12:.1f}" text-anchor="end" font-size="23" font-family="Georgia,serif" fill="#2E5680">managed</text>'
            f'<text x="{W-R-8}" y="{Y(plain[-1])+30:.1f}" text-anchor="end" font-size="23" font-family="Georgia,serif" fill="#8A857A">plain</text></svg>')


CHANGELOG_TEXT = {
    "top20_bsc_value": (L("Top-20 + BSC + value", "Top-20 + BSC + 價值"), None, L("product core", "產品核心"), "win"),
    "top10": (L("Top-10 concentration", "Top-10 集中"), L("Sharpe tie; worse under BSC", "Sharpe 打平;BSC 下更差"), L("not adopted", "不採用"), ""),
    "uncapped_leverage": (L("Uncapped leverage", "無 cap 槓桿"), L("native max 1.49×; cap ~free", "原生上限 1.49×;cap 幾乎免費"), L("cap 1.0 kept", "保留 cap 1.0"), ""),
    "dm_bear_gate": (L("DM (2016) bear-state gate", "DM(2016)熊市閘門"), L("whipsaw; all variants &lt; BSC", "whipsaw;所有變體 &lt; BSC"), L("dropped", "剔除"), "neg"),
    "residual_momentum": (L("Residual momentum (2011)", "殘差動能(2011)"), L("corr 0.94; no gain in NDX", "相關 0.94;NDX 內無改善"), L("dropped (this universe)", "剔除(本股池)"), "neg"),
    "value_weighted": (L("Cap-weighted top-20 (SEC shares)", "市值加權 top-20(SEC 股數)"), L("excess over QQQ goes to zero", "對 QQQ 超額歸零"), L("EW kept; Table 4 recaptioned", "維持等權;Table 4 改註"), "neg"),
}


def main():
    note = json.load(open(NOTE, encoding="utf-8"))
    css = open(CSS, encoding="utf-8").read()
    t1f, t1r = note["table1_umd"]["full"], note["table1_umd"]["recent20"]
    t4, t5, hold = note["table4_decomposition"], note["table5_crisis"], note["holdings"]

    t1_rows = "".join(
        f'<tr><td>{r["window"]}</td><td>{pct(r["ann"], True)}</td><td>{num(r["sharpe"])}</td>'
        f'<td>{num(r["t"])}</td><td class="neg">{num(r["skew"])}</td><td class="neg">{pct(r["worstMonth"])}</td></tr>'
        for r in (t1f, t1r))

    t2_rows = "".join(
        f'<tr><td>{r["month"]}</td><td class="neg">{pct(r["plain"])}</td>'
        f'<td class="neg">{pct(r["managed"])}</td><td>{num(r["weight"])}</td></tr>'
        for r in note["table2_crash"])

    label_map = {
        "sleeve_plain": L("AlphaSync sleeve, plain", "AlphaSync sleeve,裸版"),
        "sleeve_managed": L("AlphaSync sleeve, managed", "AlphaSync sleeve,管理版"),
    }
    t3_rows = "".join(
        f'<tr><td>{label_map.get(r["series"], r["series"])}</td><td>{r["vs"]}</td><td>{num(r["beta"])}</td>'
        f'<td class="{"neg" if r["alpha"] < 0 else ""}">{pct(r["alpha"], True)}</td>'
        f'<td class="{"neg" if r["tAlpha"] < 0 else ""}">{num(r["tAlpha"])}</td></tr>'
        for r in note["table3_attribution"])

    t6_rows = ""
    for c in note["changelog"]:
        trial, result, decision, cls = CHANGELOG_TEXT[c["trial"]]
        if c["trial"] == "top20_bsc_value":
            result = L(f'α≈0; crisis {pct(t5["managed"])} vs SPY {pct(t5["spy"])}',
                       f'α≈0;危機月 {pct(t5["managed"])} vs SPY {pct(t5["spy"])}')
        t6_rows += (f'<tr><td>{c["n"]}</td><td class="left">{trial}</td>'
                    f'<td class="left">{result}</td><td class="left {cls}">{decision}</td></tr>')

    holdings_cells = "".join(f"<span>{t}</span>" for t in hold["tickers"])

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaSync : Research Notes</title>
<meta name="description" content="A literature-based momentum implementation with volatility-managed risk control, documented as a public research note.">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
{css}
</style>
</head>
<body>
<div class="note-root" data-lang="en" id="root">
<div class="sheet">
  <div class="langbar">
    <button id="btn-en" class="on" onclick="setLang('en')">EN</button>
    <button id="btn-zh" onclick="setLang('zh')">中文</button>
  </div>

  <div class="series">{L("AlphaSync · Research Notes", "AlphaSync · 研究筆記")}<span class="no">No. 1 · July 2026</span></div>

  <h1>{L("A Literature-Based Momentum Implementation, with Volatility-Managed Risk Control",
        "一個以文獻為本的動能實作,搭配波動率管理的風控")}</h1>
  <p class="byline">alphasync.capital · <span class="ver">{L(f'Specification {note["spec"]}, locked {note["specLocked"]}',
        f'規格 {note["spec"]},鎖定於 {note["specLocked"]}')}</span> · <a href="#s6">{L("changelog", "變更日誌")}</a></p>

  <section class="abstract">
    <h2>{L("Abstract", "摘要")}</h2>
    <p class="en">AlphaSync implements two published results on a point-in-time Nasdaq-100 universe:
    cross-sectional momentum (Jegadeesh &amp; Titman 1993) and volatility-managed momentum
    (Barroso &amp; Santa-Clara 2015). We claim no proprietary alpha. The evidence for the premium
    comes from the literature, which rests on 99 years of U.S. data and on replications in other
    markets, not from this backtest. This page documents how much of the published premium remains
    in a long-only, no-leverage portfolio that a retail investor can execute, and records the layers
    we tested and discarded along the way.</p>
    <p class="zh">AlphaSync 在 point-in-time 的 Nasdaq-100 股票池上實作兩個已發表的結果:橫斷面動能(Jegadeesh &amp; Titman
    1993)與波動率管理動能(Barroso &amp; Santa-Clara 2015)。我們不宣稱自有 alpha。溢酬的證據來自文獻,建立在 99
    年的美國資料與其他市場的複製上,而不是這份回測。本頁記錄的是,已發表的溢酬放進一個 long-only、無槓桿、散戶可執行的組合之後還剩多少,以及過程中我們測試後捨棄的那些層。</p>
  </section>

  <h2 class="sec"><span class="n">1</span>{L("Evidence, in three tiers", "三層證據")}</h2>
  <p class="en">Every number is labeled by its source of evidence. <i>Literature</i>: results established by
  peer-reviewed research on 1927–present data. <i>Replication</i>: those results reproduced independently
  by our pipeline from primary data.<sup><a href="#fn1">1</a></sup> <i>Live record</i>: our own
  out-of-sample history, which is still too short to carry statistical weight, so we do not use it as
  evidence.</p>
  <p class="zh">每個數字都標注它的證據來源。<i>文獻(Literature)</i>:由同儕審查研究在 1927
  年至今資料上建立的結果。<i>複製(Replication)</i>:那些結果由我們的管線從原始資料獨立重現。<sup><a href="#fn1">1</a></sup>
  <i>實盤紀錄(Live record)</i>:我們自己的樣本外歷史,目前還太短,撐不起統計推論,所以我們不把它當作證據。</p>

  <div class="tbl"><table>
    <caption><b>Table 1.</b> {L("The momentum factor (UMD), Ken French data, monthly. A 20-year window has little statistical power for a premium with a Sharpe ratio near 0.5, so inference has to rest on the full sample.",
    "動能因子(UMD),Ken French 資料,月頻。對 Sharpe 約 0.5 的溢酬,20 年窗口幾乎沒有檢定力,推論只能依靠完整樣本。")}</caption>
    <thead><tr><th>{L("Window", "窗口")}</th><th>{L("Ann. return", "年化報酬")}</th><th>Sharpe</th><th><i>t</i></th><th>{L("Skew", "偏度")}</th><th>{L("Worst month", "最差月")}</th></tr></thead>
    <tbody>{t1_rows}</tbody>
  </table></div>

  <h2 class="sec"><span class="n">2</span>{L("What risk management can and cannot fix", "風控能修什麼、不能修什麼")}</h2>
  <p class="en">In our replication, the volatility-managed variant improves the Sharpe ratio by 1.78× in the
  paper's own sample and by 1.80× in the strictly post-publication window. The improvement comes from the
  crash months rather than from the premium itself, since volatility management changes exposure and not
  the signal. In each of the major crash months, the rule entered the month holding less than half of its
  normal exposure:</p>
  <p class="zh">在我們的複製裡,波動率管理版把 Sharpe 在論文自身的樣本內改善了 1.78 倍,在嚴格發表後的窗口改善了 1.80
  倍。改善來自崩盤月份,而不是溢酬本身,因為波動率管理改變的是曝險,不是訊號。在每一個主要崩盤月,這條規則進場時的曝險都不到平常的一半:</p>

  <div class="tbl"><table>
    <caption><b>Table 2.</b> {L("Momentum crash months, plain vs. managed (our replication, French daily data). Weight shown is the rule's <i>ex-ante</i> exposure.",
    "動能崩盤月份,裸版 vs 管理版(我們的複製,French 日資料)。權重為規則的<i>事前</i>曝險。")}</caption>
    <thead><tr><th>{L("Month", "月份")}</th><th>{L("Plain", "裸版")}</th><th>{L("Managed", "管理版")}</th><th>{L("Weight", "持有權重")}</th></tr></thead>
    <tbody>{t2_rows}</tbody>
  </table></div>

  <figure>{fig1_svg(note["fig1"])}
    <figcaption><b>Figure 1.</b> {L("Cumulative growth (log scale), plain vs. volatility-managed momentum, 1927–2026. Generated from the research pipeline (French daily data); the managed variant scales exposure by inverse realized volatility.",
    "累積成長(對數座標),裸版 vs 波動率管理動能,1927–2026。由研究管線生成(French 日資料);管理版以實現波動的倒數縮放曝險。")}</figcaption>
  </figure>

  <h2 class="sec"><span class="n">3</span>{L("Attribution: where every basis point comes from", "歸因:每一個基點從哪裡來")}</h2>
  <p class="en">We regress the sleeve's monthly returns on benchmarks an investor can hold for a few basis
  points, and read the intercept as the implementation's alpha. Before running the regressions we expected
  an intercept indistinguishable from zero, because the sleeve is built from a published signal on a widely
  tracked index. The estimates in Table 3 are consistent with that expectation.<sup><a href="#fn2">2</a></sup></p>
  <p class="zh">我們把 sleeve 的月報酬,對「花幾個基點就能持有的基準」做回歸,把截距項讀作這個實作的 alpha。在跑回歸之前,我們的預期是截距與零無法區分,因為
  sleeve 用的是已發表的訊號,跑在一個被廣泛追蹤的指數上。Table 3 的估計與這個預期一致。<sup><a href="#fn2">2</a></sup></p>

  <div class="tbl"><table>
    <caption><b>Table 3.</b> {L("CAPM attribution, monthly, our pipeline. MTUM shown as the honest yardstick for live long-only momentum.",
    "CAPM 歸因,月頻,我們的管線。MTUM 作為 live long-only 動能的誠實量尺。")}</caption>
    <thead><tr><th>{L("Series", "序列")}</th><th>{L("vs.", "對照")}</th><th>β</th><th>α (ann.)</th><th><i>t</i>(α)</th></tr></thead>
    <tbody>{t3_rows}</tbody>
  </table></div>

  <p class="en">Table 4 decomposes where the sleeve's return comes from. In this sample, equal-weighting
  the index costs return relative to QQQ, and momentum selection earns most of it back. Trial #6 then
  checks the weighting itself, since the selection effect could come from the equal-weight size tilt
  rather than from the ranking. A cap-weighted variant of the same top-20 shows no excess over QQQ, so we
  read the selection effect as a joint result of momentum ranking and the equal-weight tilt.</p>
  <p class="zh">Table 4 拆解 sleeve 的報酬從哪裡來。在本樣本裡,把指數等權化相對 QQQ
  會損失報酬,而動能選股把大部分賺回來。試驗 #6 接著檢查加權方式本身,因為選股效果有可能來自等權的 size
  傾斜,而不是排序。同一組 top-20 改成市值加權後對 QQQ 沒有超額,所以我們把選股效果解讀為動能排序與等權傾斜的共同結果。</p>

  <div class="tbl"><table>
    <caption><b>Table 4.</b> {L(f'Decomposition, gross, common window. The equal-weight selection effect ({pct(t4["selectionAnn"], True)}/yr, <i>t</i> {num(t4["selectionT"])}) does not survive cap-weighting: the value-weighted variant&#39;s excess over QQQ is {pct(t4["vwExcessAnn"], True)}/yr (<i>t</i> {num(t4["vwExcessT"])}). Neither is statistically significant at this sample length.',
    f'拆解,毛報酬,共同窗口。等權選股效果({pct(t4["selectionAnn"], True)}/年,<i>t</i> {num(t4["selectionT"])})未能在市值加權下存活:市值加權版對 QQQ 的超額為 {pct(t4["vwExcessAnn"], True)}/年(<i>t</i> {num(t4["vwExcessT"])})。在此樣本長度下兩者統計上皆不顯著。')}</caption>
    <thead><tr><th>{L("Portfolio", "組合")}</th><th>{L("Ann.", "年化")}</th><th>Sharpe</th></tr></thead>
    <tbody>
      <tr><td>{L("QQQ (cap-weight NDX)", "QQQ(市值加權 NDX)")}</td><td>{pct(t4["qqq"]["ann"])}</td><td>{num(t4["qqq"]["sharpe"])}</td></tr>
      <tr><td>{L("Equal-weight all NDX (no selection)", "等權全 NDX(無選股)")}</td><td>{pct(t4["ewNdx"]["ann"])}</td><td>{num(t4["ewNdx"]["sharpe"])}</td></tr>
      <tr><td>{L("Momentum top-20, equal-weight (sleeve)", "動能 top-20,等權(sleeve)")}</td><td>{pct(t4["sleeve"]["ann"])}</td><td>{num(t4["sleeve"]["sharpe"])}</td></tr>
      <tr><td>{L("Momentum top-20, cap-weight (trial #6)", "動能 top-20,市值加權(試驗 #6)")}</td><td>{pct(t4["vwSleeve"]["ann"])}</td><td>{num(t4["vwSleeve"]["sharpe"])}</td></tr>
      <tr class="rule-top"><td>{L("→ selection effect, equal-weight space", "→ 選股效果(等權空間)")}</td><td class="win">{pct(t4["selectionAnn"], True)}</td><td>{num(t4["selectionSharpe"])}</td></tr>
      <tr><td>{L("→ excess over QQQ, cap-weight space", "→ 對 QQQ 超額(市值加權空間)")}</td><td class="neg">{pct(t4["vwExcessAnn"], True)}</td><td>—</td></tr>
    </tbody>
  </table></div>

  <p class="en">Table 5 reports behavior in the ten worst S&amp;P 500 months of the sample. The managed
  sleeve fell less than the index it selects from in these months, which is where the volatility layer
  does its work:</p>
  <p class="zh">Table 5 報告樣本中標普 500 最差十個月的表現。在這些月份,管理版 sleeve 跌得比它選股的指數少,波動率管理層的作用主要出現在這裡:</p>

  <div class="tbl"><table>
    <caption><b>Table 5.</b> {L("Mean return across the 10 worst S&amp;P 500 months, 2015–2026.", "標普 500 最差 10 個月的平均報酬,2015–2026。")}</caption>
    <thead><tr><th>SPY</th><th>QQQ</th><th>{L("Sleeve", "sleeve")}</th><th>{L("Managed", "管理版")}</th><th>{L("+ Value 50/50", "+價值 50/50")}</th></tr></thead>
    <tbody><tr><td class="neg">{pct(t5["spy"])}</td><td class="neg">{pct(t5["qqq"])}</td><td class="neg">{pct(t5["sleeve"])}</td>
    <td class="win">{pct(t5["managed"])}</td><td>{pct(t5["combo5050"])}</td></tr></tbody>
  </table></div>

  <h2 class="sec"><span class="n">4</span>{L("Known failure modes", "已知失敗模式")}</h2>
  <p class="en">The momentum factor was statistically flat from 2006 to 2026, and three-year windows are
  often negative. A holder of this sleeve should expect stretches like that to recur; we have no way of
  making them easier to sit through, and do not claim to. If the optional value sleeve is enabled, note
  that value contributed negative returns over the last two decades, so the case for it rests on the
  1927–present record and on cross-market evidence rather than on recent performance.</p>
  <p class="zh">動能因子在 2006–2026 統計上是趴平的,而且三年窗口常常為負。持有這個 sleeve
  的人應該預期這種時期會再出現;我們沒有辦法讓它變得好熬,也不宣稱可以。如果啟用可選的價值 sleeve,請注意價值在過去二十年的貢獻是負的,所以支持它的理由來自
  1927 年至今的紀錄與跨市場證據,而不是近期表現。</p>
  <p class="en">We also record what we tested and rejected. Three literature-based layers were tried on this
  universe and discarded, each with its expectation registered before the run:</p>
  <p class="zh">我們也記錄我們測試後否決的東西。三個有文獻依據的層在這個股票池上試過之後被捨棄,每一個的預期都在跑之前先登記:</p>

  <div class="tbl"><table>
    <caption><b>Table 6.</b> {L("Change log (excerpt). The full log is public; each trial counts against the multiple-testing budget.",
    "變更日誌(節錄)。完整日誌是公開的;每次試驗都計入多重檢定的預算。")}</caption>
    <thead><tr><th>#</th><th>{L("Trial", "試驗")}</th><th>{L("Result", "結果")}</th><th>{L("Decision", "決策")}</th></tr></thead>
    <tbody>{t6_rows}</tbody>
  </table></div>

  <h2 class="sec"><span class="n">5</span>{L("Current portfolio", "本月持倉")}</h2>
  <p class="note-dim">{L(f'Top-20 by 12-1 momentum, formation {hold["month"]}. Published after execution. Mean one-way turnover {hold["turnoverMeanPct"]:g}%/mo; estimated cost drag ~{hold["costDragBpsYr"]:g} bps/yr.',
  f'依 12-1 動能排序的前 20 名,成型月 {hold["month"]}。於執行後公布。平均單邊換手率 {hold["turnoverMeanPct"]:g}%/月;估計成本拖累約 {hold["costDragBpsYr"]:g} bps/年。')}</p>
  <div class="holdings-grid">{holdings_cells}</div>

  <h2 class="sec" id="s6"><span class="n">6</span>{L("Method &amp; changelog", "方法與變更日誌")}</h2>
  <p class="en">The full specification and every change to it are public. The numbers previously published
  on this site came from the retired v6 backtest, whose universe was assembled with hindsight, so we
  withdrew them because a backtest on a hindsight universe cannot be interpreted. The withdrawal is itself
  an entry in the changelog.</p>
  <p class="zh">完整規格與它的每一次變更都是公開的。本站先前發布的數字來自已退役的 v6
  回測,它的股票池是回頭看著歷史挑出來的,所以我們把那些數字撤下了,因為建立在後見之明股票池上的回測沒有辦法解讀。這次撤下本身也是變更日誌裡的一筆。</p>

  <h2 class="sec">{L("References", "參考文獻")}</h2>
  <ul class="refs">
    <li>Jegadeesh, N., and S. Titman. 1993. "Returns to Buying Winners and Selling Losers." <i>Journal of Finance</i> 48 (1): 65–91.</li>
    <li>Barroso, P., and P. Santa-Clara. 2015. "Momentum Has Its Moments." <i>Journal of Financial Economics</i> 116 (1): 111–120.</li>
    <li>Daniel, K., and T. Moskowitz. 2016. "Momentum Crashes." <i>Journal of Financial Economics</i> 122 (2): 221–247.</li>
    <li>Blitz, D., J. Huij, and M. Martens. 2011. "Residual Momentum." <i>Journal of Empirical Finance</i> 18 (3): 506–521.</li>
    <li>Bailey, D. H., and M. López de Prado. 2014. "The Deflated Sharpe Ratio." <i>Journal of Portfolio Management</i> 40 (5): 94–107.</li>
  </ul>

  <div class="fnotes">
    <p id="fn1">1. {L(f'Pipeline: point-in-time Nasdaq-100 membership; prices include delisted members ({note["coverage"]["pct"]}% member-month coverage). The remaining gaps are listed in the repository.',
    f'管線:point-in-time Nasdaq-100 成員資格;價格含已下市成員(成員月覆蓋率 {note["coverage"]["pct"]}%)。剩下的缺口列在 repository 裡。')}</p>
    <p id="fn2">2. {L("A zero α is the expected outcome for this implementation. The page reports exposures, risk control, and attribution; it does not claim outperformance.",
    "對這個實作而言,α 為零是預期中的結果。本頁報告的是曝險、風控與歸因,並不宣稱能打敗基準。")}</p>
  </div>
</div>
</div>
<script>
function setLang(l) {{
  document.getElementById('root').setAttribute('data-lang', l);
  document.getElementById('btn-en').classList.toggle('on', l === 'en');
  document.getElementById('btn-zh').classList.toggle('on', l === 'zh');
}}
</script>
</body>
</html>
"""
    os.makedirs(SITE, exist_ok=True)
    out = os.path.join(SITE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {os.path.abspath(out)} ({os.path.getsize(out)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
