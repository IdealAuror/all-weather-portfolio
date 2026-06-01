"""实验日志 — 每次回测追加一行 JSONL。

每条记录含时间戳、git hash、核心指标子集、结论。
用 pandas 读取：pd.read_json('experiments.jsonl', lines=True)
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "experiments.jsonl"


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return "unknown"


def save_run(perf_results: dict, metrics: dict, conclusion: str = "") -> Path:
    """将本次回测核心指标追加到实验日志。

    Args:
        perf_results: {(port, tier): perf_metrics dict}
        metrics: step_3 返回的完整指标 dict
        conclusion: 用户填写的测试结论
    """
    records = {}
    for (port, tier), m in perf_results.items():
        if tier == "100% RP":
            records[port] = {
                "cagr": m["cagr"],
                "vol": m["vol"],
                "mdd": m["mdd"],
                "sharpe": m["sharpe"],
                "calmar": m["calmar"],
                "cum_return": m["cum_return"],
            }

    ws = {}
    for port, s in metrics.get("weight_stability", {}).items():
        ws[port] = {
            "monthly_turnover": s["monthly_turnover_mean"],
            "eff_n": s["effective_n_mean"],
            "cost_drag": s["cost_drag_annual"],
        }

    rc = {}
    for port, buckets in metrics.get("risk_contrib_tv", {}).items():
        rc[port] = {b: v["mean"] for b, v in buckets.items()
                    if not b.startswith("_")}

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "git_hash": _git_hash(),
        "conclusion": conclusion,
        "metrics": records,
        "weight_stability": ws,
        "risk_contrib": rc,
    }

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return LOG_FILE


def list_runs(n: int = 5) -> list[dict]:
    """列出最近 n 次实验。"""
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    return lines[-n:]
