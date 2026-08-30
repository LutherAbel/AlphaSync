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
    <p class="en">AlphaSync implements published results on a Nasdaq-100 universe: cross-sectional momentum
    (Jegadeesh &amp; Titman 1993) and volatility-managed momentum (Barroso &amp; Santa-Clara 2015).
    The strategy claims no proprietary alpha. The evidence for the premium is the literature, 99
    years of U.S. data and replication across 24 markets, not this backtest. What this page adds is
    an honest account of implementation: what survives dilution to a long-only, no-leverage,
    retail-executable portfolio, and every layer we tested and discarded, documented before you invest.</p>
    <p class="zh">AlphaSync 在 Nasdaq-100 股票池上實作已發表的結果:橫斷面動能(Jegadeesh &amp; Titman 1993)與波動率管理動能(Barroso
    &amp; Santa-Clara 2015)。本策略不宣稱任何自有 alpha。溢酬的證據來自文獻,99 年的美國資料與跨 24
    個市場的複製,不是這份回測。本頁面加上的是一份誠實的實作紀錄:在稀釋成 long-only、無槓桿、散戶可執行的組合後還剩下什麼,以及每一層我們測過又捨棄的東西,都在你投資前先寫清楚。</p>
  </section>

  <h2 class="sec"><span class="n">1</span>{L("Evidence, in three tiers", "三層證據")}</h2>
  <p class="en">Every number is labeled by its source of evidence. <i>Literature</i>: results established by
  peer-reviewed research on 1927–present data. <i>Replication</i>: those results reproduced independently
  by our pipeline from primary data.<sup><a href="#fn1">1</a></sup> <i>Live record</i>: our own
  out-of-sample history, which is short, and which we refuse to extrapolate from.</p>
  <p class="zh">每個數字都標注它的證據來源。<i>文獻(Literature)</i>:由同儕審查研究在 1927
  年至今資料上建立的結果。<i>複製(Replication)</i>:那些結果由我們的管線從原始資料獨立重現。<sup><a href="#fn1">1</a></sup>
  <i>實盤紀錄(Live record)</i>:我們自己的樣本外歷史,它很短,而我們拒絕從它外推。</p>

  <div class="tbl"><table>
    <caption><b>Table 1.</b> {L("The momentum factor (UMD), Ken French data, monthly. A 20-year window has no statistical power for a Sharpe-0.5 premium; the full-sample <i>t</i> does.",
    "動能因子(UMD),Ken French 資料,月頻。20 年窗口對 Sharpe 0.5 的溢酬沒有統計檢定力;完整樣本的 <i>t</i> 才有。")}</caption>
    <thead><tr><th>{L("Window", "窗口")}</th><th>{L("Ann. return", "年化報酬")}</th><th>Sharpe</th><th><i>t</i></th><th>{L("Skew", "偏度")}</th><th>{L("Worst month", "最差月")}</th></tr></thead>
    <tbody>{t1_rows}</tbody>
  </table></div>

  <h2 class="sec"><span class="n">2</span>{L("What risk management can and cannot fix", "風控能修什麼、不能修什麼")}</h2>
  <p class="en">Volatility management repairs momentum's crash profile; it does not resurrect a dead premium.
  In our replication, the managed variant improves Sharpe by 1.78× in the paper's own sample and by 1.80×
  in the strictly post-publication window. Every major historical crash is attenuated the same way:</p>
  <p class="zh">波動率管理修的是動能的崩盤形狀,它救不回一個已死的溢酬。在我們的複製裡,管理版在論文自己的樣本內把 Sharpe 改善 1.78
  倍,在嚴格發表後的窗口改善 1.80 倍。每一次重大歷史崩盤都以同樣方式被削弱:</p>

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
  <p class="en">We regress returns on benchmarks you could hold for a few basis points. Whatever the betas
  absorb is not ours. The intercept, with its honest <i>t</i>-statistic, is the only number anyone is
  entitled to call alpha, and on our Nasdaq-100 sleeve it is statistically indistinguishable from
  zero.<sup><a href="#fn2">2</a></sup></p>
  <p class="zh">我們把報酬對「你花幾個基點就能持有的基準」做回歸。beta 吸收掉的都不是我們的。截距項,連同它誠實的 <i>t</i>
  值,是唯一有資格被稱為 alpha 的數字,而在我們的 Nasdaq-100 sleeve 上,它與零在統計上無法區分。<sup><a href="#fn2">2</a></sup></p>

  <div class="tbl"><table>
    <caption><b>Table 3.</b> {L("CAPM attribution, monthly, our pipeline. MTUM shown as the honest yardstick for live long-only momentum.",
    "CAPM 歸因,月頻,我們的管線。MTUM 作為 live long-only 動能的誠實量尺。")}</caption>
    <thead><tr><th>{L("Series", "序列")}</th><th>{L("vs.", "對照")}</th><th>β</th><th>α (ann.)</th><th><i>t</i>(α)</th></tr></thead>
    <tbody>{t3_rows}</tbody>
  </table></div>

  <p class="en">Zero alpha over the index is not the same as zero contribution. Decomposing the sleeve shows
  where the work actually happens: equal-weighting a mega-cap index costs return, and momentum selection
  earns it back. But we also cross-validated the weighting itself (trial #6): a cap-weighted variant of the
  same top-20 shows <i>no</i> excess over QQQ. The selection effect below is therefore a property of the
  equal-weight implementation, a momentum-plus-size-tilt composite, not momentum alone.</p>
  <p class="zh">對指數的 alpha 為零,不等於貢獻為零。把 sleeve
  拆解,可以看到力氣實際上花在哪:等權一個大市值指數會損失報酬,而動能選股把它賺回來。但我們也對加權方式本身做了交叉驗證(試驗
  #6):同一組 top-20 改成市值加權後,對 QQQ <i>沒有</i>任何超額。因此下表的選股效果是等權實作的性質,是「動能 + size
  傾斜」的複合,不是動能單獨的功勞。</p>

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

  <p class="en">The product's real edge shows up not in average return but in the worst months. Across the
  ten worst months for the S&amp;P 500, the managed sleeve fell less than the index it selects from:</p>
  <p class="zh">產品真正的優勢不在平均報酬,而在最差的月份。在標普 500 最慘的十個月裡,管理版 sleeve 跌得比它選股的指數更少:</p>

  <div class="tbl"><table>
    <caption><b>Table 5.</b> {L("Mean return across the 10 worst S&amp;P 500 months, 2015–2026.", "標普 500 最差 10 個月的平均報酬,2015–2026。")}</caption>
    <thead><tr><th>SPY</th><th>QQQ</th><th>{L("Sleeve", "sleeve")}</th><th>{L("Managed", "管理版")}</th><th>{L("+ Value 50/50", "+價值 50/50")}</th></tr></thead>
    <tbody><tr><td class="neg">{pct(t5["spy"])}</td><td class="neg">{pct(t5["qqq"])}</td><td class="neg">{pct(t5["sleeve"])}</td>
    <td class="win">{pct(t5["managed"])}</td><td>{pct(t5["combo5050"])}</td></tr></tbody>
  </table></div>

  <h2 class="sec"><span class="n">4</span>{L("Known failure modes", "已知失敗模式")}</h2>
  <p class="en">Momentum's premium has survived 99 years <i>because</i> it is periodically intolerable: the
  factor spent 2006–2026 statistically flat, and any three-year window can be negative. If you enable the
  optional value sleeve, we disclose up front that value contributed <i>negative</i> returns for the last
  two decades; its case rests on century-scale and cross-market evidence, not recent form. If you cannot
  hold through that, this product is not for you, and no risk gate we ship will change it.</p>
  <p class="zh">動能的溢酬活了 99 年,<i>正是因為</i>它週期性地令人難以忍受:這個因子在 2006–2026
  統計上趴平,任何三年窗口都可能為負。如果你啟用可選的價值 sleeve,我們事先揭露:價值在過去二十年貢獻為<i>負</i>;它的依據是百年尺度與跨市場的證據,不是近期表現。如果你抱不過這個,這個產品不適合你,而我們出的任何風控閘門都改變不了這件事。</p>
  <p class="en">We also publish what we <i>tried and rejected</i>. Three literature-backed layers were tested
  on this universe and discarded because they did not earn their place, each with its result pre-registered
  before the run:</p>
  <p class="zh">我們也公開我們<i>測過又否決</i>的東西。三個有文獻背書的層在這個股票池上被測試後捨棄,因為它們沒有掙到自己的位置,每一個的結果都在跑之前就先登記:</p>

  <div class="tbl"><table>
    <caption><b>Table 6.</b> {L("Change log (excerpt). The full log is public as a commitment device; each trial counts against multiple-testing budget.",
    "變更日誌(節錄)。完整日誌公開作為一種承諾機制;每次試驗都計入多重檢定預算。")}</caption>
    <thead><tr><th>#</th><th>{L("Trial", "試驗")}</th><th>{L("Result", "結果")}</th><th>{L("Decision", "決策")}</th></tr></thead>
    <tbody>{t6_rows}</tbody>
  </table></div>

  <h2 class="sec"><span class="n">5</span>{L("Current portfolio", "本月持倉")}</h2>
  <p class="note-dim">{L(f'Top-20 by 12-1 momentum, formation {hold["month"]}. Published after execution. Mean one-way turnover {hold["turnoverMeanPct"]:g}%/mo; estimated cost drag ~{hold["costDragBpsYr"]:g} bps/yr.',
  f'依 12-1 動能排序的前 20 名,成型月 {hold["month"]}。於執行後公布。平均單邊換手率 {hold["turnoverMeanPct"]:g}%/月;估計成本拖累約 {hold["costDragBpsYr"]:g} bps/年。')}</p>
  <div class="holdings-grid">{holdings_cells}</div>

  <h2 class="sec" id="s6"><span class="n">6</span>{L("Method &amp; changelog", "方法與變更日誌")}</h2>
  <p class="en">The full specification and every change to it are public. Numbers previously published on
  this site (the retired v6 backtest) have been withdrawn; they used a hindsight-selected universe and are
  not interpretable. That correction is itself logged.</p>
  <p class="zh">完整規格與它的每一次變更都是公開的。本站先前發布的數字(退役的 v6
  回測)已撤下;它們使用了後見之明選出的股票池,無法解讀。這個更正本身也被記錄下來。</p>

  <h2 class="sec">{L("References", "參考文獻")}</h2>
  <ul class="refs">
    <li>Jegadeesh, N., and S. Titman. 1993. "Returns to Buying Winners and Selling Losers." <i>Journal of Finance</i> 48 (1): 65–91.</li>
    <li>Barroso, P., and P. Santa-Clara. 2015. "Momentum Has Its Moments." <i>Journal of Financial Economics</i> 116 (1): 111–120.</li>
    <li>Daniel, K., and T. Moskowitz. 2016. "Momentum Crashes." <i>Journal of Financial Economics</i> 122 (2): 221–247.</li>
    <li>Blitz, D., J. Huij, and M. Martens. 2011. "Residual Momentum." <i>Journal of Empirical Finance</i> 18 (3): 506–521.</li>
    <li>Bailey, D. H., and M. López de Prado. 2014. "The Deflated Sharpe Ratio." <i>Journal of Portfolio Management</i> 40 (5): 94–107.</li>
  </ul>

  <div class="fnotes">
    <p id="fn1">1. {L(f'Pipeline: point-in-time Nasdaq-100 membership; prices include delisted members ({note["coverage"]["pct"]}% member-month coverage). Coverage gaps are published, not patched over.',
    f'管線:point-in-time Nasdaq-100 成員資格;價格含已下市成員(成員月覆蓋率 {note["coverage"]["pct"]}%)。覆蓋缺口公開,不做掩蓋。')}</p>
    <p id="fn2">2. {L("An expected-zero α is not failure. The product is the exposure, the risk control, and this accounting, not a claim to beat the benchmark.",
    "預期為零的 α 不是失敗。產品是曝險、風控、和這份帳目,不是一個打敗基準的宣稱。")}</p>
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
