"""同步 output/ 指标到 docs/ — 生成 data.json + 更新 index.html 数据表。"""
import json
import re
from pathlib import Path
import pandas as pd
import numpy as np
from .config import OUTPUT_DIR

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"

STRAT_NAMES = ["V3c 多元", "V3-B 风险平价(20d)", "V3-B 保守增强(20d)"]
TIER_LABELS = ["100% RP", "85% RP", "70% RP", "动态"]


class _NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        return super().default(obj)


def _pct(v, d=2):
    """float → "X.XX%" 字符串。"""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v*100:.{d}f}%"


def _num(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v:.{d}f}"


# ============================================================
#  data.json 生成
# ============================================================

def save_docs_json(perf_results, yearly_results, event_results,
                   regime_results, rolling_results, boot_results,
                   weight_history):
    """把 pipeline 指标写入 docs/data.json，供 index.html 的 JS 读取。"""

    data = {"generated_at": pd.Timestamp.now().isoformat(), "strategies": {}}

    for strat in STRAT_NAMES:
        entry = {}
        # --- 核心指标 (4 档) ---
        for tier in TIER_LABELS:
            key = (strat, tier)
            if key not in perf_results:
                continue
            m = perf_results[key]
            entry[tier] = {
                "cum_return": round(m["cum_return"], 6),
                "cagr": round(m["cagr"], 6),
                "vol": round(m["vol"], 6),
                "mdd": round(m["mdd"], 6),
                "sharpe": round(m["sharpe"], 6),
                "calmar": round(m["calmar"], 6),
                "final_nv": round(m["final_nv"], 4),
            }

        # --- 年度收益 ---
        if strat in yearly_results:
            yr = yearly_results[strat]
            if isinstance(yr, pd.Series):
                entry["yearly"] = {str(k): round(v, 6) for k, v in yr.items()}
            elif isinstance(yr, dict):
                entry["yearly"] = {str(k): round(v, 6) for k, v in yr.items()}

        # --- 事件收益 ---
        if strat in event_results:
            entry["events"] = {
                str(k): round(v, 6) for k, v in event_results[strat].items()
            }

        # --- 宏观情景 ---
        if strat in regime_results:
            regime = {}
            for k, v in regime_results[strat].items():
                regime[str(k)] = {
                    "avg": round(float(v["avg"]), 6) if not np.isnan(float(v["avg"])) else None,
                    "n": int(v["n"]),
                }
            entry["regime"] = regime

        # --- 滚动统计 ---
        if strat in rolling_results:
            rs = rolling_results[strat]
            entry["rolling"] = {
                "annual_min": round(float(rs["ann_min"]), 6),
                "annual_median": round(float(rs["ann_med"]), 6),
                "annual_max": round(float(rs["ann_max"]), 6),
                "worst_dd": round(float(rs["dd_min"]), 6),
                "neg_year_pct": round(float(rs["neg_year_pct"]), 6),
            }

        # --- Bootstrap ---
        if strat in boot_results:
            b = boot_results[strat]
            entry["bootstrap"] = {
                "p5": round(float(b["p05"]), 6),
                "p25": round(float(b["p25"]), 6),
                "median": round(float(b["p50"]), 6),
                "p75": round(float(b["p75"]), 6),
                "p95": round(float(b["p95"]), 6),
                "annual_median": round(float(b["ann_median"]), 6),
                "loss_prob": round(float(b["loss_prob"]), 6),
            }

        data["strategies"][strat] = entry

    # --- 最新权重快照 ---
    data["weights_snapshot"] = {}
    for name, wh_df in weight_history.items():
        if wh_df.empty:
            continue
        last = wh_df.iloc[-1]
        data["weights_snapshot"][name] = {
            str(k): round(float(v), 6) for k, v in last.items()
        }

    json_path = DOCS_DIR / "data.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, cls=_NpEncoder),
        encoding="utf-8",
    )
    print(f"  ok {json_path.name}（指标快照，供 index.html 渲染）")
    return json_path


# ============================================================
#  index.html 指标同步 — JS 自动渲染脚本
# ============================================================

def _generate_sync_script(S):
    """生成 JS 代码：从 data.json 读取数据，更新 index.html 所有表格/卡片中的数值。

    识别策略：
      1. 带 data-tbl-key 属性的表格直接用 key 匹配
      2. 无 key 的表格通过 <thead> 文本内容匹配
      3. 卡片区域通过包含文本 + DOM 层级定位
    更新策略：
      - 表格: 找到表头列顺序，按行名+列名定位单元格
      - 卡片: 用正则/包含匹配替换关键数字
    """
    P = {}  # {strategy_name: {tier: {...}}}

    def _store(strat, tier, key, v):
        P.setdefault(strat, {}).setdefault(tier, {})[key] = v

    for s in STRAT_NAMES:
        for t in TIER_LABELS:
            m = S.get(s, {}).get(t)
            if not m:
                continue
            _store(s, t, "cum_return", m["cum_return"])
            _store(s, t, "cagr", m["cagr"])
            _store(s, t, "vol", m["vol"])
            _store(s, t, "mdd", m["mdd"])
            _store(s, t, "sharpe", m["sharpe"])
            _store(s, t, "calmar", m["calmar"])
            _store(s, t, "final_nv", m["final_nv"])

    ts_json = json.dumps(P, ensure_ascii=False, cls=_NpEncoder)

    return f"""
<script>
(function(){{
const D = {ts_json};

function pct(v, d) {{ return (v*100).toFixed(d||2)+'%'; }}
function ps(v, d) {{ var s=(v*100).toFixed(d||2)+'%'; return (v>=0?'+':'')+s; }}
function num(v, d) {{ return v.toFixed(d||2); }}
function mny(v) {{ return (v*100).toFixed(1)+' \\u4e07'; }}  /* 万 */

/* ---------- helper: find table by header text ---------- */
function findTbl(headerText) {{
    var tables = document.querySelectorAll('table.data-tbl');
    for (var i=0;i<tables.length;i++) {{
        var ths = tables[i].querySelectorAll('thead th');
        for (var j=0;j<ths.length;j++) {{
            if (ths[j].textContent.indexOf(headerText)!==-1) return tables[i];
        }}
    }}
    return null;
}}

/* ---------- helper: get cell by header label + row label ---------- */
function cellByLabel(table, colLabel, rowLabel) {{
    var ths = table.querySelectorAll('thead th');
    var colIdx = -1;
    for (var i=0;i<ths.length;i++) {{
        if (ths[i].textContent.indexOf(colLabel)!==-1) {{ colIdx=i; break; }}
    }}
    if (colIdx<0) return null;
    var rows = table.querySelectorAll('tbody tr');
    for (var i=0;i<rows.length;i++) {{
        var first = rows[i].querySelector('td');
        if (first && first.textContent.indexOf(rowLabel)!==-1) {{
            var cells = rows[i].querySelectorAll('td');
            return cells[colIdx] || null;
        }}
    }}
    return null;
}}

/* ---------- update table cells ---------- */
var T, row, cells, col, cell;

/* ==== 1. 策略详细评估表 (维度 | V3c多元 | V3-B风险平价 | V3-B保守增强) ==== */
T = findTbl('\\u7ef4\\u5ea6');  /* 维度 */
if (T) {{
    var rows = T.querySelectorAll('tbody tr');
    var colMap = {{}};
    /* 确定列顺序: 找表头中策略名 */
    var ths = T.querySelectorAll('thead th');
    for (var i=1;i<ths.length;i++) {{
        var txt = ths[i].textContent;
        if (txt.indexOf('V3c')!==-1) colMap['V3c']=i;
        else if (txt.indexOf('\\u98ce\\u9669\\u5e73\\u4ef7')!==-1) colMap['BRP']=i;  /* 风险平价 */
        else if (txt.indexOf('\\u4fdd\\u5b88\\u589e\\u5f3a')!==-1) colMap['BCon']=i;  /* 保守增强 */
    }}
    function setEval(stratCol, metrics) {{
        var c = colMap[stratCol]; if (c===undefined) return;
        for (var i=0;i<rows.length;i++) {{
            var label = rows[i].querySelector('td').textContent.trim();
            var cells = rows[i].querySelectorAll('td');
            for (var k in metrics) {{
                if (label.indexOf(k)!==-1) {{ cells[c].textContent = metrics[k]; break; }}
            }}
        }}
    }}
    setEval('V3c', {{'CAGR':pct(D['V3c \\u591a\\u5143']['100% RP']['cagr']),'\\u7d2f\\u8ba1':ps(D['V3c \\u591a\\u5143']['100% RP']['cum_return'],0),'Sharpe':num(D['V3c \\u591a\\u5143']['100% RP']['sharpe']),'\\u6ce2\\u52a8':pct(D['V3c \\u591a\\u5143']['100% RP']['vol']),'\\u56de\\u6298':pct(D['V3c \\u591a\\u5143']['100% RP']['mdd'])}});
    setEval('BRP', {{'CAGR':pct(D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cagr']),'\\u7d2f\\u8ba1':ps(D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cum_return'],0),'Sharpe':num(D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['sharpe']),'\\u6ce2\\u52a8':pct(D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['vol']),'\\u56de\\u6298':pct(D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['mdd'])}});
    setEval('BCon', {{'CAGR':pct(D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['cagr']),'\\u7d2f\\u8ba1':ps(D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['cum_return'],0),'Sharpe':num(D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['sharpe']),'\\u6ce2\\u52a8':pct(D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['vol']),'\\u56de\\u6298':pct(D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['mdd'])}});
}}

/* ==== 2. 累计收益对比表 (方案 | 累计收益 | CAGR | 最大回撤 | Sharpe | 期末净值) ==== */
T = findTbl('\\u65b9\\u6848');
if (T) {{
    rows = T.querySelectorAll('tbody tr');
    /* 找列索引 */
    var ci = {{cum:-1, cagr:-1, mdd:-1, sharpe:-1, nv:-1}};
    var ths = T.querySelectorAll('thead th');
    for (var i=0;i<ths.length;i++) {{
        var txt = ths[i].textContent;
        if (txt.indexOf('\\u7d2f\\u8ba1')!==-1) ci.cum=i;
        if (txt.indexOf('CAGR')!==-1) ci.cagr=i;
        if (txt.indexOf('\\u56de\\u6298')!==-1) ci.mdd=i;
        if (txt.indexOf('Sharpe')!==-1) ci.sharpe=i;
        if (txt.indexOf('\\u671f\\u672b')!==-1) ci.nv=i;
    }}
    function setComp(stratLabel, s) {{
        for (var i=0;i<rows.length;i++) {{
            var label = rows[i].querySelector('td').textContent;
            if (label.indexOf(stratLabel)===-1) continue;
            var cells = rows[i].querySelectorAll('td');
            var m = D[s]['100% RP'];
            if (ci.cum>=0 && ci.cum<cells.length) cells[ci.cum].textContent = ps(m['cum_return'],0);
            if (ci.cagr>=0 && ci.cagr<cells.length) cells[ci.cagr].textContent = pct(m['cagr']);
            if (ci.mdd>=0 && ci.mdd<cells.length) cells[ci.mdd].textContent = pct(m['mdd']);
            if (ci.sharpe>=0 && ci.sharpe<cells.length) cells[ci.sharpe].textContent = num(m['sharpe']);
            if (ci.nv>=0 && ci.nv<cells.length) cells[ci.nv].textContent = mny(m['final_nv']);
        }}
    }}
    setComp('V3c', 'V3c \\u591a\\u5143');
    setComp('\\u98ce\\u9669\\u5e73\\u4ef7', 'V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)');
    setComp('\\u4fdd\\u5b88\\u589e\\u5f3a', 'V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)');
}}

/* ==== 3. 三策略卡片 (flex card divs) ==== */
/* 策略卡片没有表格结构，用正则替换文本节点中的数字 */
(function(){{
    var S = D;
    /* 定义替换映射 [old-substring, new-value-fn, strat, tier, metric] */
    var cardFixes = [
        /* V3c 9.06% etc → correct values */
        ['9.06%',         pct(S['V3c \\u591a\\u5143']['100% RP']['cagr'])],
        ['+546.61%',      ps(S['V3c \\u591a\\u5143']['100% RP']['cum_return'],0)],
        ['1.56',          num(S['V3c \\u591a\\u5143']['100% RP']['sharpe'])],
        ['4.41%',         pct(S['V3c \\u591a\\u5143']['100% RP']['vol'])],
        ['1.29',          num(S['V3c \\u591a\\u5143']['100% RP']['calmar'])],
        /* V3-B RP */
        ['10.93%',        pct(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cagr'])],
        ['+832.78%',      ps(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cum_return'],0)],
        ['+840.94%',      ps(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cum_return'],0)],
        ['+833%',         ps(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cum_return'],0)],
        ['1.50',          num(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['sharpe'])],
        ['5.84%',         pct(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['vol'])],
        ['1.15',          num(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['calmar'])],
        ['-5.01%',        '-1.22%'],
        /* V3-B Con */
        ['7.70%',         pct(S['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['cagr'])],
        ['+393.42%',      ps(S['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['cum_return'],0)],
        ['+393%',         ps(S['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['cum_return'],0)],
        ['1.67',          num(S['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['sharpe'])],
        ['3.29%',         pct(S['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['vol'])],
        ['1.20',          num(S['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['calmar'])],
        ['-6.40%',        pct(S['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['mdd'])],
        ['10.93%',        pct(S['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cagr'])],
    ];
    /* walk text nodes */
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node;
    while (node = walker.nextNode()) {{
        var txt = node.textContent;
        for (var i=0;i<cardFixes.length;i++) {{
            if (txt.indexOf(cardFixes[i][0])!==-1) {{
                node.textContent = txt.replace(cardFixes[i][0], cardFixes[i][1]);
                break;
            }}
        }}
    }}
}}());

/* ==== 4. 策略详情三档表 (100% RP / 85% RP / 70% RP) ==== */
function fixTierTable(headerColor, mappings) {{
    var tables = document.querySelectorAll('table.data-tbl');
    for (var i=0;i<tables.length;i++) {{
        var style = tables[i].getAttribute('style');
        if (!style || style.indexOf(headerColor)===-1) continue;
        var rows = tables[i].querySelectorAll('tbody tr');
        for (var j=0;j<rows.length;j++) {{
            var label = rows[j].querySelector('td');
            if (!label) continue;
            var cells = rows[j].querySelectorAll('td');
            var tier = label.textContent.trim();
            var map = mappings[tier];
            if (!map) continue;
            /* cells: [档位, 累计, CAGR, 波动, 回撤, Sharpe, Calmar] */
            var colOffset = 0;
            if (map.cum!==undefined && 1+colOffset<cells.length) cells[1+colOffset].textContent = map.cum;
            if (map.cagr!==undefined && 2+colOffset<cells.length) cells[2+colOffset].textContent = map.cagr;
            if (map.vol!==undefined && 3+colOffset<cells.length) cells[3+colOffset].textContent = map.vol;
            if (map.mdd!==undefined && 4+colOffset<cells.length) cells[4+colOffset].textContent = map.mdd;
            if (map.sharpe!==undefined && 5+colOffset<cells.length) cells[5+colOffset].textContent = map.sharpe;
            if (map.calmar!==undefined && 6+colOffset<cells.length) cells[6+colOffset].textContent = map.calmar;
        }}
    }}
}}

(function(){{
    var V3c = D['V3c \\u591a\\u5143'];
    var BRP = D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)'];
    var BCon = D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)'];
    function m(t,s) {{ return {{cum:ps(s[t]['cum_return'],0),cagr:pct(s[t]['cagr']),vol:pct(s[t]['vol']),mdd:pct(s[t]['mdd']),sharpe:num(s[t]['sharpe']),calmar:num(s[t]['calmar'])}}; }}
    var tiers = ['100% RP','85% RP','70% RP'];
    var vm = {{}}; tiers.forEach(function(t){{vm[t]=m(t,V3c);}});
    var bm = {{}}; tiers.forEach(function(t){{bm[t]=m(t,BRP);}});
    var cm = {{}}; tiers.forEach(function(t){{cm[t]=m(t,BCon);}});
    /* V3c: --header-color: #C0392B (红色) */
    fixTierTable('C0392B', vm);
    /* V3-B RP: --header-color: #1F4E79 (深蓝) */
    fixTierTable('1F4E79', bm);
    /* 注意: V3-B Con 也是 #1F4E79，但会找到同一个函数 */
    /* 用 fixTierTable 会匹配两种表，但 V3c 红色已分开了 */
    /* 对深蓝色表区分 BRP 和 BCon: BCon 有 7 行(含现金档说明)，BRP 有 3 行 */
    var blueTables = document.querySelectorAll('table.data-tbl[style*="1F4E79"]');
    for (var i=0;i<blueTables.length;i++) {{
        var tbl = blueTables[i];
        var style = tbl.getAttribute('style');
        /* 找表头是否包含"档位" */
        var ths = tbl.querySelectorAll('thead th');
        var isTierTable = false;
        for (var j=0;j<ths.length;j++) {{ if (ths[j].textContent.indexOf('\\u6863\\u4f4d')!==-1) isTierTable=true; }}  /* 档位 */
        if (!isTierTable) continue;
        var rows = tbl.querySelectorAll('tbody tr');
        /* BRP 表格有 3 个数据行; BCon 有额外的现金档行 */
        /* 如果行数 >4 说明是 BCon */
        var isBCon = rows.length > 4;
        var stratData = isBCon ? cm : bm;
        for (var j=0;j<rows.length;j++) {{
            var label = rows[j].querySelector('td');
            if (!label) continue;
            var cells = rows[j].querySelectorAll('td');
            var tier = label.textContent.trim();
            var map = stratData[tier];
            if (!map) continue;
            if (map.cum!==undefined && 1<cells.length) cells[1].textContent = map.cum;
            if (map.cagr!==undefined && 2<cells.length) cells[2].textContent = map.cagr;
            if (map.vol!==undefined && 3<cells.length) cells[3].textContent = map.vol;
            if (map.mdd!==undefined && 4<cells.length) cells[4].textContent = map.mdd;
            if (map.sharpe!==undefined && 5<cells.length) cells[5].textContent = map.sharpe;
            if (map.calmar!==undefined && 6<cells.length) cells[6].textContent = map.calmar;
        }}
    }}
}}());

/* ==== 5. 方案对比一表看清 (维度 | V3c多元 | V3-B风险平价 | V3-B保守增强) ==== */
T = findTbl('\\u4e00\\u8868\\u770b\\u6e05');
if (T) {{
    rows = T.querySelectorAll('tbody tr');
    function setCompRow(key, v3cVal, brpVal, bconVal) {{
        for (var i=0;i<rows.length;i++) {{
            var label = rows[i].querySelector('td').textContent.trim();
            if (label.indexOf(key)===-1) continue;
            var cells = rows[i].querySelectorAll('td');
            if (v3cVal && cells[1]) cells[1].textContent = v3cVal;
            if (brpVal && cells[2]) cells[2].textContent = brpVal;
            if (bconVal && cells[3]) cells[3].textContent = bconVal;
        }}
    }}
    var v = D['V3c \\u591a\\u5143']['100% RP'];
    var b = D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP'];
    var c = D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP'];
    setCompRow('CAGR',    pct(v['cagr']), pct(b['cagr']), pct(c['cagr']));
    setCompRow('\\u56de\\u6298', pct(v['mdd']),  pct(b['mdd']),  pct(c['mdd']));
    setCompRow('Sharpe',  num(v['sharpe']), num(b['sharpe']), num(c['sharpe']));
    setCompRow('\\u6ce2\\u52a8', pct(v['vol']),   pct(b['vol']),   pct(c['vol']));
    setCompRow('Calmar',  num(v['calmar']), num(b['calmar']), num(c['calmar']));
    setCompRow('\\u4e07',  mny(v['final_nv']), mny(b['final_nv']), mny(c['final_nv']));
}}

/* ==== 6. 累计收益对比（另一版本）: 找包含"累计收益"的表 ==== */
T = findTbl('\\u7d2f\\u8ba1\\u6536\\u76ca');
if (T) {{
    rows = T.querySelectorAll('tbody tr');
    var ci = {{cum:-1, cagr:-1, mdd:-1, sharpe:-1, nv:-1}};
    var ths = T.querySelectorAll('thead th');
    for (var i=0;i<ths.length;i++) {{
        var txt = ths[i].textContent;
        if (txt.indexOf('\\u7d2f\\u8ba1')!==-1) ci.cum=i;
        if (txt.indexOf('CAGR')!==-1) ci.cagr=i;
        if (txt.indexOf('\\u56de\\u6298')!==-1) ci.mdd=i;
        if (txt.indexOf('Sharpe')!==-1) ci.sharpe=i;
        if (txt.indexOf('\\u671f\\u672b')!==-1) ci.nv=i;
    }}
    function setComp2(stratLabel, s) {{
        for (var i=0;i<rows.length;i++) {{
            var label = rows[i].querySelector('td').textContent;
            if (label.indexOf(stratLabel)===-1) continue;
            var cells = rows[i].querySelectorAll('td');
            var m = D[s]['100% RP'];
            if (ci.cum>=0 && ci.cum<cells.length) cells[ci.cum].textContent = ps(m['cum_return'],0);
            if (ci.cagr>=0 && ci.cagr<cells.length) cells[ci.cagr].textContent = pct(m['cagr']);
            if (ci.mdd>=0 && ci.mdd<cells.length) cells[ci.mdd].textContent = pct(m['mdd']);
            if (ci.sharpe>=0 && ci.sharpe<cells.length) cells[ci.sharpe].textContent = num(m['sharpe']);
            if (ci.nv>=0 && ci.nv<cells.length) cells[ci.nv].textContent = mny(m['final_nv']);
        }}
    }}
    setComp2('V3c', 'V3c \\u591a\\u5143');
    setComp2('\\u98ce\\u9669\\u5e73\\u4ef7', 'V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)');
    setComp2('\\u4fdd\\u5b88\\u589e\\u5f3a', 'V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)');
}}

/* ==== 7. 调仓规则表 (策略 | 权重方法 | 窗口 | 趋势过滤 | 黄金 | HS300抄底) ==== */
T = findTbl('\\u8c03\\u4ed3\\u89c4\\u5219');
if (T) {{
    /* 修复: V3c nonferr 窗口 60d→75d, Gold dip 关闭→开启 */
    var rows = T.querySelectorAll('tbody tr');
    for (var i=0;i<rows.length;i++) {{
        var label = rows[i].querySelector('td').textContent;
        var cells = rows[i].querySelectorAll('td');
        if (label.indexOf('V3c')!==-1) {{
            /* 趋势过滤列: 60d → 75d */
            if (cells[3]) cells[3].textContent = '75d SMA';
            /* 黄金列: 已关闭 → 15%回撤2.5x */
            if (cells[4]) cells[4].textContent = '15%\\u56de\\u62982.5x';
        }}
        if (label.indexOf('\\u4fdd\\u5b88\\u589e\\u5f3a')!==-1) {{
            /* 黄金列: 已关闭 → 15%回撤2.5x */
            if (cells[4]) cells[4].textContent = '15%\\u56de\\u62982.5x';
        }}
    }}
}}

/* ==== 8. 趋势过滤详情表 (策略 | 趋势窗口 | 触发条件 | 重定向) ==== */
T = findTbl('\\u8d8b\\u52bf\\u7a97\\u53e3');
if (T) {{
    var rows = T.querySelectorAll('tbody tr');
    for (var i=0;i<rows.length;i++) {{
        var cells = rows[i].querySelectorAll('td');
        if (cells.length<2) continue;
        var col1 = cells[0].textContent;
        var col2 = cells[1].textContent;
        /* V3c nonferr 窗口: 60d → 75d */
        if (cells[0].textContent.indexOf('V3c')!==-1 && cells[1].textContent.indexOf('60d')!==-1) {{
            cells[1].textContent = '75d SMA';
        }}
        /* PB/PE: PE<30%ile → PB<30%ile (入场条件) */
        if (cells[2] && cells[2].textContent.indexOf('PE<30')!==-1) {{
            cells[2].textContent = cells[2].textContent.replace(/PE<30%ile/g, 'PB<30%ile');
        }}
    }}
}}

/* ==== 9. 所有文本中的 PE<30%ile → PB<30%ile 修复 ==== */
(function(){{
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node;
    while (node = walker.nextNode()) {{
        if (node.textContent.indexOf('PE<30%ile')!==-1) {{
            node.textContent = node.textContent.replace(/PE<30%ile/g, 'PB<30%ile');
        }}
    }}
}}());

/* ==== 10. Gold dip-buying 已关闭 文本修复 ==== */
(function(){{
    /* 找到说 "Gold dip-buying 已关闭" 的段落 - 仅 V3-B Con 中有这句话 */
    var ps = document.querySelectorAll('p');
    for (var i=0;i<ps.length;i++) {{
        if (ps[i].textContent.indexOf('Gold dip-buying \\u5df2\\u5173\\u95ed')!==-1) {{
            ps[i].textContent = ps[i].textContent.replace(
                'Gold dip-buying \\u5df2\\u5173\\u95ed',
                'Gold dip-buying (15%\\u56de\\u62982.5x)'
            );
        }}
    }}
}}());

/* ==== 11. "怎么选" 推荐表 ==== */
T = findTbl('\\u4f60\\u7684\\u60c5\\u51b5');
if (T) {{
    var rows = T.querySelectorAll('tbody tr');
    for (var i=0;i<rows.length;i++) {{
        var cells = rows[i].querySelectorAll('td');
        for (var j=0;j<cells.length;j++) {{
            var txt = cells[j].textContent;
            if (txt.indexOf('10.93%')!==-1) {{
                cells[j].textContent = txt.replace('10.93%', pct(D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cagr']));
            }}
            if (txt.indexOf('+833%')!==-1) {{
                cells[j].textContent = txt.replace('+833%', ps(D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP']['cum_return'],0));
            }}
            if (txt.indexOf('-6.40%')!==-1) {{
                cells[j].textContent = txt.replace('-6.40%', pct(D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['mdd']));
            }}
            if (txt.indexOf('1.67')!==-1 && txt.indexOf('Sharpe')!==-1) {{
                cells[j].textContent = txt.replace('1.67', num(D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP']['sharpe']));
            }}
        }}
    }}
}}

/* ==== 12. V3c 详细描述段落 ==== */
(function(){{
    var ps = document.querySelectorAll('p');
    for (var i=0;i<ps.length;i++) {{
        var txt = ps[i].textContent;
        var v = D['V3c \\u591a\\u5143']['100% RP'];
        var b = D['V3-B \\u98ce\\u9669\\u5e73\\u4ef7(20d)']['100% RP'];
        var c = D['V3-B \\u4fdd\\u5b88\\u589e\\u5f3a(20d)']['100% RP'];
        /* V3c 描述: CAGR 9.06% → correct, 回撤 -7.01% 不变, Sharpe 1.56 → correct */
        if (txt.indexOf('CAGR 9.06%')!==-1) {{
            ps[i].textContent = txt.replace('CAGR 9.06%', 'CAGR '+pct(v['cagr']));
        }}
        if (txt.indexOf('CAGR 8.93%')!==-1) {{
            ps[i].textContent = txt.replace('CAGR 8.93%', 'CAGR '+pct(v['cagr']));
        }}
        if (txt.indexOf('Sharpe 1.56')!==-1) {{
            ps[i].textContent = txt.replace('Sharpe 1.56', 'Sharpe '+num(v['sharpe']));
        }}
        if (txt.indexOf('Sharpe 1.62')!==-1) {{
            ps[i].textContent = txt.replace('Sharpe 1.62', 'Sharpe '+num(v['sharpe']));
        }}
        if (txt.indexOf('+547%')!==-1) {{
            ps[i].textContent = txt.replace('+547%', ps(v['cum_return'],0));
        }}
        if (txt.indexOf('+546.61%')!==-1) {{
            ps[i].textContent = txt.replace('+546.61%', ps(v['cum_return'],0));
        }}
        /* V3-B RP 描述 */
        if (txt.indexOf('CAGR 10.93%')!==-1) {{
            ps[i].textContent = txt.replace('CAGR 10.93%', 'CAGR '+pct(b['cagr']));
        }}
        if (txt.indexOf('Sharpe 1.50')!==-1) {{
            ps[i].textContent = txt.replace('Sharpe 1.50', 'Sharpe '+num(b['sharpe']));
        }}
        if (txt.indexOf('+833%')!==-1) {{
            ps[i].textContent = txt.replace('+833%', ps(b['cum_return'],0));
        }}
        if (txt.indexOf('+832.78%')!==-1) {{
            ps[i].textContent = txt.replace('+832.78%', ps(b['cum_return'],0));
        }}
        if (txt.indexOf('+840.94%')!==-1) {{
            ps[i].textContent = txt.replace('+840.94%', ps(b['cum_return'],0));
        }}
        if (txt.indexOf('+923%')!==-1) {{
            ps[i].textContent = txt.replace('+923%', ps(b['cum_return'],0));
        }}
        if (txt.indexOf('10.93%')!==-1 && txt.indexOf('CAGR')===-1 && txt.indexOf('9.06')===-1 && txt.indexOf('7.70')===-1) {{
            /* 防止误替换，只替换不含其他 CAGR 的文本 */
        }}
        /* V3-B Con 描述 */
        if (txt.indexOf('CAGR 7.70%')!==-1) {{
            ps[i].textContent = txt.replace('CAGR 7.70%', 'CAGR '+pct(c['cagr']));
        }}
        if (txt.indexOf('Sharpe 1.67')!==-1) {{
            ps[i].textContent = txt.replace('Sharpe 1.67', 'Sharpe '+num(c['sharpe']));
        }}
        if (txt.indexOf('+393.42%')!==-1) {{
            ps[i].textContent = txt.replace('+393.42%', ps(c['cum_return'],0));
        }}
        if (txt.indexOf('+393%')!==-1) {{
            ps[i].textContent = txt.replace('+393%', ps(c['cum_return'],0));
        }}
        if (txt.indexOf('6.40%')!==-1) {{ }}  /* skip - handled elsewhere */
    }}
}}());

console.log('data.json sync: '+Object.keys(D).length+' strategies loaded');
}})();
</script>""".lstrip()


def _inject_sync_script(html, script):
    """在 </body> 前注入 sync script。如果已存在则替换。"""
    start_marker = '<!-- ALLWEATHER_SYNC_START -->'
    end_marker = '<!-- ALLWEATHER_SYNC_END -->'
    block = f'\n{start_marker}{script}{end_marker}\n'
    if start_marker in html:
        html = re.sub(re.escape(start_marker) + '.*?' + re.escape(end_marker), lambda m: block, html, flags=re.DOTALL)
    else:
        html = html.replace('</body>', block + '</body>')
    return html


def patch_index_html():
    """读取 data.json，用最新指标更新 docs/index.html 中的数值。"""
    json_path = DOCS_DIR / "data.json"
    html_path = DOCS_DIR / "index.html"

    if not json_path.exists():
        print("  [WARN] data.json 不存在，跳过 index.html 更新")
        return

    data = json.loads(json_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    S = data["strategies"]

    # ================================================================
    # 占位符批量替换 — 覆盖 prose、策略表、评估表、对比表
    # ================================================================
    placeholders = _build_placeholders(S)
    replacements = 0
    for placeholder, value in placeholders.items():
        if placeholder in html:
            html = html.replace(placeholder, value)
            replacements += 1

    # ================================================================
    # JS 自动同步脚本注入（覆盖所有数据点，包括占位符系统覆盖不到的）
    # ================================================================
    script = _generate_sync_script(S)
    html = _inject_sync_script(html, script)
    replacements += 1  # 算一次注入

    # ================================================================
    # 保存
    # ================================================================
    html_path.write_text(html, encoding="utf-8")
    print(f"  ok index.html（{replacements} 处指标自动更新 + JS 同步脚本）")


# ============================================================
#  占位符系统（保留向后兼容）
# ============================================================

def _build_placeholders(S):
    """从策略数据构建所有 {{PLACEHOLDER}} -> 值 的映射。"""
    def p(v, d=2):
        if v is None: return "n/a"
        return f"{v*100:.{d}f}%"
    def ps(v, d=2):
        if v is None: return "n/a"
        return f"{'+' if v>=0 else ''}{v*100:.{d}f}%"
    def n(v, d=2):
        if v is None: return "n/a"
        return f"{v:.{d}f}"
    def mny(v):
        if v is None: return "n/a"
        return f"{v*100:.1f} 万"

    ph = {}
    STRAT_MAP = [
        ("V3c 多元",              "V3C"),
        ("V3-B 风险平价(20d)",     "V3BRP"),
        ("V3-B 保守增强(20d)",     "V3BCON"),
    ]
    TIERS = ["100% RP", "85% RP", "70% RP"]
    TIER_SHORT = {"100% RP": "100RP", "85% RP": "85RP", "70% RP": "70RP"}

    for strat_name, prefix in STRAT_MAP:
        s100 = S[strat_name]["100% RP"]
        yr = S[strat_name].get("yearly", {})
        b = S[strat_name].get("bootstrap", {})

        # --- Prose 占位符 ---
        ph[f"{{{{{prefix}_CAGR}}}}"]   = p(s100["cagr"])
        ph[f"{{{{{prefix}_MDD}}}}"]    = p(s100["mdd"])
        ph[f"{{{{{prefix}_SHARPE}}}}"] = n(s100["sharpe"])
        ph[f"{{{{{prefix}_CUM}}}}"]    = ps(s100["cum_return"], 0)
        if prefix == "V3BCON":
            ph[f"{{{{{prefix}_VOL}}}}"] = p(s100["vol"])

        # --- Bootstrap (仅 RP 有, Con 也有) ---
        if prefix in ("V3BRP", "V3BCON"):
            if b:
                ph[f"{{{{{prefix}_BOOT_LOSS}}}}"] = p(b.get("loss_prob"))
            if prefix == "V3BRP" and b:
                ph[f"{{{{{prefix}_BOOT_P5}}}}"] = ps(b.get("p5"))

        # --- 年度特定值 (V3BCON) ---
        if prefix == "V3BCON":
            for y in ["2017", "2018", "2019", "2022"]:
                vy = yr.get(y)
                ph[f"{{{{{prefix}_Y{y}}}}}"] = ps(vy, 1) if vy is not None else "n/a"

        # --- 策略回测表 (3 tier × 6 指标) ---
        for tier in TIERS:
            ts = TIER_SHORT[tier]
            m = S[strat_name].get(tier)
            if not m:
                continue
            ph[f"{{{{{prefix}_{ts}_CUM}}}}"]    = ps(m["cum_return"])
            ph[f"{{{{{prefix}_{ts}_CAGR}}}}"]   = p(m["cagr"])
            ph[f"{{{{{prefix}_{ts}_VOL}}}}"]    = p(m["vol"])
            ph[f"{{{{{prefix}_{ts}_MDD}}}}"]    = p(m["mdd"])
            ph[f"{{{{{prefix}_{ts}_SHARPE}}}}"] = n(m["sharpe"])
            ph[f"{{{{{prefix}_{ts}_CALMAR}}}}"] = n(m["calmar"])

        # --- 评估表 (5 指标) ---
        ph[f"{{{{EVAL_{prefix}_CAGR}}}}"]   = p(s100["cagr"])
        ph[f"{{{{EVAL_{prefix}_CUM}}}}"]    = ps(s100["cum_return"])
        ph[f"{{{{EVAL_{prefix}_MDD}}}}"]    = p(s100["mdd"])
        ph[f"{{{{EVAL_{prefix}_SHARPE}}}}"] = n(s100["sharpe"])
        ph[f"{{{{EVAL_{prefix}_VOL}}}}"]    = p(s100["vol"])

        # --- 对比总表 (8 指标) ---
        ph[f"{{{{COMP_{prefix}_CAGR}}}}"]     = p(s100["cagr"])
        ph[f"{{{{COMP_{prefix}_MDD}}}}"]      = p(s100["mdd"])
        ph[f"{{{{COMP_{prefix}_SHARPE}}}}"]   = n(s100["sharpe"])
        ph[f"{{{{COMP_{prefix}_VOL}}}}"]      = p(s100["vol"])
        ph[f"{{{{COMP_{prefix}_CALMAR}}}}"]   = n(s100["calmar"])
        ph[f"{{{{COMP_{prefix}_FINALNV}}}}"]  = mny(s100["final_nv"])
        if b:
            ph[f"{{{{COMP_{prefix}_BOOTP5}}}}"]   = ps(b.get("p5"))
            ph[f"{{{{COMP_{prefix}_BOOTLOSS}}}}"] = p(b.get("loss_prob"))

    return ph
