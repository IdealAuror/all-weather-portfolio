"""同步 output/ 指标到 docs/ — 生成 data.json + 更新 index.html 数据表。"""
import json
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
#  index.html 指标同步
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


def patch_index_html():
    """读取 data.json，用最新指标更新 docs/index.html 中的数值。

    通过正则匹配 HTML 结构中稳定的上下文来定位每个数据格，
    不依赖 HTML 注释或 data-* 属性，避免编码/编辑工具兼容问题。
    """
    json_path = DOCS_DIR / "data.json"
    html_path = DOCS_DIR / "index.html"

    if not json_path.exists():
        print("  [WARN] data.json 不存在，跳过 index.html 更新")
        return

    data = json.loads(json_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    S = data["strategies"]
    replacements = 0

    # ================================================================
    # 占位符批量替换 — 覆盖 prose、策略表、评估表、对比表
    # ================================================================
    placeholders = _build_placeholders(S)
    for placeholder, value in placeholders.items():
        if placeholder in html:
            html = html.replace(placeholder, value)
            replacements += 1

    # ================================================================
    # 保存
    # ================================================================
    html_path.write_text(html, encoding="utf-8")
    print(f"  ok index.html（{replacements} 处指标自动更新）")
