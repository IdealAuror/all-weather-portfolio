"""桥水全天候策略 · 中国版回测 - 主入口。

用法：
    python main.py            跑完整回测流程（默认输出 CSV/JSON/Excel/Markdown）
    python main.py --fetch    （可选）先拉取数据再回测
    python main.py --no-excel 跳过 Excel 综合报告
    python main.py --help     查看所有命令
"""
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="桥水全天候策略中国版回测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  python main.py               跑回测（默认）
  python main.py --fetch       先拉数据再回测
  python main.py --fetch-only  只拉数据不回测
  python main.py --force-fetch 重新拉取所有数据（覆盖已有 CSV）
  python main.py --no-excel    跳过 Excel 综合报告
  python main.py --no-markdown 跳过 Markdown 综合报告
  python main.py --note '结论'  附带结论写入实验日志
  python main.py --list-experiments  查看实验记录
""",
    )
    parser.add_argument("--fetch", action="store_true",
                        help="先拉取数据再回测（仅补缺失的）")
    parser.add_argument("--fetch-only", action="store_true",
                        help="只拉取数据，不跑回测")
    parser.add_argument("--force-fetch", action="store_true",
                        help="强制重新拉取所有数据（覆盖已有）")
    parser.add_argument("--start", default=None, metavar="YYYYMMDD",
                        help="拉取数据起始日期，如 20180101（默认 20150101）")
    parser.add_argument("--end", default=None, metavar="YYYYMMDD",
                        help="拉取数据结束日期，如 20251231（默认 20251231）")
    parser.add_argument("--no-excel", action="store_true",
                        help="跳过 Excel 综合报告（默认会生成）")
    parser.add_argument("--no-markdown", action="store_true",
                        help="跳过 Markdown 综合报告（默认会生成）")
    parser.add_argument("--note", default="", metavar="结论",
                        help="本次测试结论，写入实验日志 experiments.jsonl")
    parser.add_argument("--list-experiments", action="store_true",
                        help="查看最近实验记录")
    args = parser.parse_args()

    # === 查看实验记录 ===
    if args.list_experiments:
        from allweather.experiment_log import list_runs
        runs = list_runs(10)
        if not runs:
            print("暂无实验记录。")
            return
        for i, r in enumerate(reversed(runs), 1):
            print(f"\n--- 实验 #{i} ---")
            print(f"  时间: {r['timestamp']}")
            print(f"  git: {r['git_hash']}")
            if r.get('conclusion'):
                print(f"  结论: {r['conclusion']}")
            for port, m in r.get("metrics", {}).items():
                print(f"  {port}: CAGR={m['cagr']*100:.2f}%  "
                      f"MDD={m['mdd']*100:.2f}%  Sharpe={m['sharpe']:.2f}")
        return

    # === 数据拉取 ===
    if args.fetch or args.fetch_only or args.force_fetch:
        print("\n" + "=" * 60)
        print("  数据拉取")
        print("=" * 60)
        from allweather.fetch import fetch_all
        kwargs = {}
        if args.start:
            kwargs["start"] = args.start
        if args.end:
            kwargs["end"] = args.end
        fetch_all(force=args.force_fetch, **kwargs)
        if args.fetch_only:
            return

    # === 检查数据齐全 ===
    from allweather.fetch import check_data_complete
    ok, missing = check_data_complete()
    if not ok:
        print(f"\n[ERROR] 缺少必需数据文件: {missing}")
        print(f"   请先运行: python main.py --fetch")
        sys.exit(1)

    # === 跑回测 ===
    from allweather.pipeline import run_full_pipeline
    run_full_pipeline(excel=not args.no_excel, markdown=not args.no_markdown,
                       note=args.note)


if __name__ == "__main__":
    main()
