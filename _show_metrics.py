import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('output/summary.json', 'r', encoding='utf-8') as f:
    all_data = json.load(f)

keys = list(all_data.keys())
strategies = {
    'V3-B 风险平价(20d) 100% RP': keys[0],
    'V3-B 保守增强(20d) 100% RP': keys[4],
    'V3c 多元 100% RP': keys[8],
}

for name, key in strategies.items():
    d = all_data[key]
    print(f'========== {name} ==========')
    print(f'{"累计收益":>12}: {d["cum_return"]*100:>7.2f}%')
    print(f'{"CAGR":>12}: {d["cagr"]*100:>7.2f}%')
    print(f'{"波动率":>12}: {d["vol"]*100:>7.2f}%')
    print(f'{"MDD":>12}: {d["mdd"]*100:>7.2f}%')
    print(f'{"Sharpe":>12}: {d["sharpe"]:>7.2f}  (rf=2.2%)')
    print(f'{"Calmar":>12}: {d["calmar"]:>7.2f}')

    yr = {k:v for k,v in d.get('yearly_returns',{}).items() if isinstance(v,(int,float))}
    pos = sum(1 for v in yr.values() if v > 0)
    neg = [k for k,v in yr.items() if isinstance(v,(int,float)) and v < 0]
    total = len(yr)
    print(f'{"正收益年比":>12}: {pos}/{total} = {pos/total*100:.0f}%  亏损年: {neg}')

    # Worst year
    if yr:
        wy = min(yr.items(), key=lambda x: x[1])
        print(f'{"最差单年":>12}: {wy[0]} = {wy[1]*100:+.2f}%')

    # Bootstrap
    bs = d.get('bootstrap', {})
    if bs and isinstance(bs, dict) and 'p05' in bs and bs['p05'] is not None:
        print(f'--- Bootstrap 5年分布 ---')
        print(f'{"5年亏损概率":>12}: {bs.get("loss_prob",0)*100:.1f}%')
        print(f'{"中位收益":>12}: {bs.get("p50",0)*100:+.2f}%')
        print(f'{"P5/P95":>12}: {bs.get("p05",0)*100:+.2f}% / {bs.get("p95",0)*100:+.2f}%')

    # D_excess
    ds = d.get('d_excess', {})
    if ds:
        print(f'--- 尾部风险 D_excess ---')
        print(f'{"D_actual":>12}: {ds.get("d_actual",0)*100:+.3f}%')
        print(f'{"Null均值":>12}: {ds.get("d_null_mean",0)*100:+.3f}%')
        print(f'{"95%CI":>12}: [{ds.get("ci_95_low",0)*100:.3f}%, {ds.get("ci_95_high",0)*100:.3f}%]')
        print(f'{"百分位":>12}: {ds.get("percentile",0)*100:.1f}%')

    # Turnover
    ws = d.get('weight_stability', {})
    if ws:
        print(f'--- 权重稳定性 ---')
        print(f'{"月均换手":>12}: {ws.get("monthly_turnover_mean",0)*100:.2f}%')
        print(f'{"月最大换手":>12}: {ws.get("monthly_turnover_max",0)*100:.2f}%')
        print(f'{"年化换手":>12}: {ws.get("annual_churn",0):.2f}x')
        print(f'{"有效资产N":>12}: {ws.get("effective_n_mean",0):.2f}')
        print(f'{"年成本拖累":>12}: {ws.get("cost_drag_annual",0)*100:.2f}%/年')

    # Rolling
    rs = d.get('rolling_stats', {})
    if rs:
        print(f'--- 滚动1年统计 ---')
        print(f'{"年化最低":>12}: {rs.get("ann_min",0)*100:.2f}%')
        print(f'{"年化中位":>12}: {rs.get("ann_med",0)*100:.2f}%')
        print(f'{"滚动1年负率":>12}: {rs.get("neg_year_pct",0)*100:.1f}%')

    # Signal counts
    sc = d.get('signal_counts', {})
    if sc:
        print(f'--- 信号触发次数 ---')
        for k, v in sc.items():
            print(f'  {k}: {v}')

    # Event returns
    ev = d.get('event_returns', {})
    if ev:
        print(f'--- 关键事件期表现 ---')
        for k, v in ev.items():
            if isinstance(v, (int,float)):
                print(f'  {k}: {v*100:+.2f}%')

    # Regime
    rg = d.get('regime_returns', {})
    if rg:
        print(f'--- 宏观情景平均季度收益 ---')
        for k, v in rg.items():
            if isinstance(v, dict):
                print(f'  {k}: {v.get("avg",0)*100:+.2f}% (n={v.get("n",0)})')

    # Risk contribution
    rc = d.get('bucket_risk_contribution', {})
    if rc and isinstance(rc, dict):
        print(f'--- 桶级风险贡献 ---')
        sum_pct = 0
        for k, v in sorted(rc.items()):
            if isinstance(v, dict) and 'mean' in v:
                print(f'  {k}: {v.get("mean",0)*100:.2f}% ±{v.get("std",0)*100:.2f}%')
                sum_pct += v.get("mean",0)
            elif isinstance(v, (int, float)):
                print(f'  {k}: {v*100:.2f}%')
                sum_pct += v
        print(f'  {"合计":>8}: {sum_pct*100:.1f}%')

    # Drawdown details
    dd = d.get('drawdown_info', {})
    if dd:
        print(f'--- 回撤详情 ---')
        for k in sorted(dd.keys()):
            v = dd[k]
            if isinstance(v, (int, float)):
                print(f'  {k}: {v*100:.2f}%')
            else:
                print(f'  {k}: {v}')

    print()
