"""桥水全天候策略 · 中国版回测 - 主入口。

用法：
    python main.py            跑完整回测流程
    python main.py --fetch    （可选）先拉取数据再回测
    python main.py --help     查看所有命令
"""
import sys
import argparse
from allweather.pipeline import run_full_pipeline
from allweather.fetch import fetch_all, check_data_complete


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
    args = parser.parse_args()

    # === 数据拉取 ===
    if args.fetch or args.fetch_only or args.force_fetch:
        print("\n" + "=" * 60)
        print("  数据拉取")
        print("=" * 60)
        kwargs = {}
        if args.start:
            kwargs["start"] = args.start
        if args.end:
            kwargs["end"] = args.end
        fetch_all(force=args.force_fetch, **kwargs)
        if args.fetch_only:
            return

    # === 检查数据齐全 ===
    ok, missing = check_data_complete()
    if not ok:
        print(f"\n[ERROR] 缺少必需数据文件: {missing}")
        print(f"   请先运行: python main.py --fetch")
        sys.exit(1)

    # === 跑回测 ===
    run_full_pipeline()


if __name__ == "__main__":
    main()
