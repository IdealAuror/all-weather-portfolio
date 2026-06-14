"""
HS300 走势统计 + 趋势过滤 SMA 窗口分析

两部分：
  Part A — HS300 走势完整统计（上/下跌段、牛熊周期、趋势持续性）
  Part B — 各 SMA 窗口在历史大跌事件中的信号时效性和假信号频率
"""

import sys
sys.path.insert(0, r"c:\Users\MOSS\Desktop\全季节策略")

import warnings
warnings.filterwarnings("ignore")

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from allweather.data import load_panel

panel = load_panel()
hs300 = panel['hs300'].dropna().copy()
rets = hs300.pct_change().dropna()
idx = hs300.index

N_YEARS = len(hs300) / 252
N_DAYS = len(hs300)

print("=" * 80)
print("  HS300 走势统计 + SMA 窗口分析")
print("=" * 80)
print(f"  数据范围: {idx[0].date()} ~ {idx[-1].date()}")
print(f"  交易日: {N_DAYS}, 约 {N_YEARS:.1f} 年")
print()

# ============================================================
# Part A-1: HS300 基本统计
# ============================================================
print("=" * 80)
print("  PART A: HS300 走势统计分析")
print("=" * 80)

cagr = (hs300.iloc[-1] / hs300.iloc[0]) ** (252 / N_DAYS) - 1
vol = rets.std() * np.sqrt(252)
max_dd = (hs300 / hs300.cummax() - 1).min()
sharpe = (cagr - 0.022) / vol
calmar = cagr / abs(max_dd)
win_month = (rets.resample('ME').apply(lambda x: (1+x).prod()-1) > 0).mean()

print(f"\n  CAGR:             {cagr:>7.2%}")
print(f"  年化波动率:       {vol:>7.2%}")
print(f"  最大回撤 (MDD):   {max_dd:>7.2%}")
print(f"  Sharpe (修正):    {sharpe:>7.2f}")
print(f"  Calmar:           {calmar:>7.2f}")
print(f"  正收益月份占比:   {win_month:>7.2%}")

# ============================================================
# Part A-2: Zigzag 转折点检测 + 上/下跌走势统计
# ============================================================
print("\n" + "=" * 80)
print("  A-2/A-3: 上/下跌走势统计（Zigzag 转折点法）")
print("=" * 80)


def find_swings(price, min_move_pct=5.0):
    """Zigzag 转折点检测。找到主要 peak/trough，要求每段幅度 >= min_move_pct。"""
    min_move = min_move_pct / 100.0
    pivots = []
    direction = None
    last_idx = 0
    last_price = price.iloc[0]

    for i in range(1, len(price) - 1):
        p = price.iloc[i]
        if direction is None:
            if p > last_price:
                direction = 1
            elif p < last_price:
                direction = -1
            last_idx = i
            last_price = p
            continue

        if direction == 1:
            if p > last_price:
                last_idx = i
                last_price = p
            elif (last_price - p) / last_price > min_move:
                pivots.append((price.index[last_idx], last_price, 'peak'))
                direction = -1
                last_idx = i
                last_price = p

        elif direction == -1:
            if p < last_price:
                last_idx = i
                last_price = p
            elif (p - last_price) / p > min_move:
                pivots.append((price.index[last_idx], last_price, 'trough'))
                direction = 1
                last_idx = i
                last_price = p

    return pivots


def swings_to_segments(price, pivots, swing_type="up"):
    """从转折点提取上/下跌段。swing_type='up': trough->peak（上涨），'down': peak->trough（下跌）"""
    segments = []
    for i in range(len(pivots) - 1):
        d1, p1, t1 = pivots[i]
        d2, p2, t2 = pivots[i + 1]

        if swing_type == "up" and t1 == 'trough' and t2 == 'peak':
            ret = p2 / p1 - 1
            segments.append({
                'start': d1, 'end': d2, 'start_price': p1, 'end_price': p2,
                'return': ret, 'trading_days': len(price[d1:d2]),
                'calendar_days': (d2 - d1).days,
            })
        elif swing_type == "down" and t1 == 'peak' and t2 == 'trough':
            ret = p2 / p1 - 1
            segments.append({
                'start': d1, 'end': d2, 'start_price': p1, 'end_price': p2,
                'return': ret, 'trading_days': len(price[d1:d2]),
                'calendar_days': (d2 - d1).days,
            })

    if not segments:
        return pd.DataFrame()
    return pd.DataFrame(segments)


for label, pct in [("5% 摆动", 5), ("10% 摆动", 10)]:
    pivots = find_swings(hs300, pct)
    n_peaks = sum(1 for _, _, t in pivots if t == 'peak')
    n_troughs = sum(1 for _, _, t in pivots if t == 'trough')
    print(f"\n  [{label}] 转折点: {n_peaks} 个峰值, {n_troughs} 个谷值")

    # 上涨段
    up_segs = swings_to_segments(hs300, pivots, "up")
    if len(up_segs) > 0:
        print(f"  上涨段: {len(up_segs)} 段")
        print(f"    交易日: 均值{up_segs['trading_days'].mean():.0f} "
              f"中位数{up_segs['trading_days'].median():.0f} "
              f"最短{up_segs['trading_days'].min():.0f} 最长{up_segs['trading_days'].max():.0f}")
        print(f"    自然日: 均值{up_segs['calendar_days'].mean():.0f} "
              f"中位数{up_segs['calendar_days'].median():.0f}")
        print(f"    涨幅: 均值{up_segs['return'].mean():.1%} 中位数{up_segs['return'].median():.1%}")
        # 长度分布
        bins = [0, 20, 40, 60, 120, 9999]
        labels_seg = ['<20d', '20-40d', '40-60d', '60-120d', '>120d']
        for bl, br, lb in zip(bins[:-1], bins[1:], labels_seg):
            cnt = ((up_segs['trading_days'] > bl) & (up_segs['trading_days'] <= br)).sum()
            if cnt > 0:
                print(f"    {lb}: {cnt} 段")

    # 下跌段
    dn_segs = swings_to_segments(hs300, pivots, "down")
    if len(dn_segs) > 0:
        print(f"  下跌段: {len(dn_segs)} 段")
        print(f"    交易日: 均值{dn_segs['trading_days'].mean():.0f} "
              f"中位数{dn_segs['trading_days'].median():.0f} "
              f"最短{dn_segs['trading_days'].min():.0f} 最长{dn_segs['trading_days'].max():.0f}")
        print(f"    跌幅: 均值{dn_segs['return'].mean():.1%} 中位数{dn_segs['return'].median():.1%}")
        # 速度分类
        fast = dn_segs[dn_segs['trading_days'] < 20]
        mid = dn_segs[(dn_segs['trading_days'] >= 20) & (dn_segs['trading_days'] < 60)]
        slow = dn_segs[dn_segs['trading_days'] >= 60]
        print(f"    急跌(<20d): {len(fast)}段 中速(20-60d): {len(mid)}段 慢熊(>=60d): {len(slow)}段")
        if len(fast) > 0:
            print(f"    急跌明细:")
            for _, r in fast.iterrows():
                print(f"      {r['start'].date()} -> {r['end'].date()}  "
                      f"{r['trading_days']}d 跌幅{r['return']:.1%}")

# ============================================================
# Part A-4: 大跌恢复时间
# ============================================================
print("\n" + "=" * 80)
print("  A-4: 大跌恢复时间（回到前高所需天数）")
print("=" * 80)

cummax = hs300.cummax()
dd_series = hs300 / cummax - 1

in_dd = (dd_series < -0.10).astype(int)
dd_entries = in_dd.diff() == 1
dd_exits = in_dd.diff() == -1
entry_dates = dd_entries[dd_entries].index
exit_dates = dd_exits[dd_exits].index

print(f"  -10% 以上回撤事件: {len(entry_dates)} 次")

recovery_stats = []
for i in range(min(len(entry_dates), len(exit_dates))):
    entry = entry_dates[i]
    exit_d = exit_dates[i]

    pre_peak = hs300[:entry].max()
    pre_peak_date = hs300[:entry].idxmax()
    trough = hs300[entry:exit_d].min()
    trough_date = hs300[entry:exit_d].idxmin()
    trough_dd = trough / pre_peak - 1
    dd_duration = len(hs300[entry:trough_date]) - 1

    recovery = hs300[trough_date:]
    recovered = recovery[recovery >= pre_peak]
    rec_days = len(hs300[trough_date:recovered.index[0]]) - 1 if len(recovered) > 0 else None

    recovery_stats.append({
        'peak_date': pre_peak_date, 'trough_date': trough_date,
        'dd_duration': dd_duration, 'trough_dd': trough_dd,
        'recovery_days': rec_days,
    })

    rec_str = f"恢复{recovered.index[0].date()}" if len(recovered) > 0 else "尚未恢复"
    print(f"  {pre_peak_date.date()} -> {trough_date.date()} "
          f"(跌{dd_duration}d, -{abs(trough_dd):.1%}) -> {rec_str} "
          f"({rec_days if rec_days else '?'}d)")

rec_ok = [r for r in recovery_stats if r['recovery_days'] is not None]
if rec_ok:
    print(f"\n  中位数恢复时间: {np.median([r['recovery_days'] for r in rec_ok]):.0f} 交易日")
    print(f"  平均恢复时间:   {np.mean([r['recovery_days'] for r in rec_ok]):.0f} 交易日")
    big = [r for r in rec_ok if r['trough_dd'] < -0.15]
    if big:
        print(f"  跌幅超15%恢复中位数: {np.median([r['recovery_days'] for r in big]):.0f} 交易日")

# ============================================================
# Part A-5: 牛熊周期 + 趋势持续性
# ============================================================
print("\n" + "=" * 80)
print("  A-5: 牛熊周期 + 趋势持续性")
print("=" * 80)

sma200 = hs300.rolling(200).mean()
bull_market = (hs300 > sma200).astype(int)
bull_pct = bull_market.mean()

# SMA200 牛熊分界
bull_days_total = bull_market.sum()
bear_days_total = len(bull_market) - bull_days_total
print(f"  SMA200 牛熊分界:")
print(f"    牛市占比: {bull_pct:.1%} ({bull_days_total:.0f}d)")
print(f"    熊市占比: {1-bull_pct:.1%} ({bear_days_total:.0f}d)")
print(f"    牛熊天数比: {bull_days_total/bear_days_total:.2f}")

# 连胜/连败统计
up_days = (rets > 0).astype(int)
down_days = (rets < 0).astype(int)

consec_up = []
c = 0
for v in up_days:
    if v:
        c += 1
    else:
        if c > 0:
            consec_up.append(c)
        c = 0
if c > 0:
    consec_up.append(c)

consec_down = []
c = 0
for v in down_days:
    if v:
        c += 1
    else:
        if c > 0:
            consec_down.append(c)
        c = 0
if c > 0:
    consec_down.append(c)

print(f"\n  趋势持续性:")
print(f"    单日上涨概率: {up_days.mean():.1%}")
print(f"    连胜: 均值{np.mean(consec_up):.1f}d 中位数{np.median(consec_up):.0f}d 最长{max(consec_up)}d")
print(f"    连败: 均值{np.mean(consec_down):.1f}d 中位数{np.median(consec_down):.0f}d 最长{max(consec_down)}d")
print(f"    连胜>=5d: {sum(1 for c in consec_up if c>=5)} 次  连败>=5d: {sum(1 for c in consec_down if c>=5)} 次")

# RSI
def rsi(price, window=14):
    delta = price.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)

rsi_vals = rsi(hs300)
print(f"    RSI14>70 (超买): {(rsi_vals>70).sum():.0f} 次 ({(rsi_vals>70).sum()/len(rsi_vals)*100:.1f}%)")
print(f"    RSI14<30 (超卖): {(rsi_vals<30).sum():.0f} 次 ({(rsi_vals<30).sum()/len(rsi_vals)*100:.1f}%)")

# 月度统计
monthly = rets.resample('ME').apply(lambda x: (1+x).prod()-1)
print(f"\n  月度统计:")
print(f"    正收益月份: {(monthly>0).mean():.1%}  负收益: {(monthly<0).mean():.1%}")
print(f"    平均月度: {monthly.mean():.2%}  中位数: {monthly.median():.2%}")
print(f"    单月>10%: {(monthly>0.10).sum()} 次  <-10%: {(monthly<-0.10).sum()} 次")
consec_loss_m = []
c = 0
for m in monthly:
    if m < 0:
        c += 1
    else:
        if c > 0:
            consec_loss_m.append(c)
        c = 0
if c > 0:
    consec_loss_m.append(c)
print(f"    最长连续下跌月份: {max(consec_loss_m) if consec_loss_m else 0}个月")

# ============================================================
# Part A-6: 历年收益
# ============================================================
print("\n" + "=" * 80)
print("  A-6: 历年收益与最大回撤")
print("=" * 80)

yearly_ret = hs300.resample('YE').apply(lambda x: x.iloc[-1] / x.iloc[0] - 1)
yearly_dd = hs300.resample('YE').apply(lambda x: (x / x.cummax() - 1).min())
for yr in yearly_ret.index:
    marker = " **" if yearly_ret.loc[yr] < -0.10 else (" *" if yearly_ret.loc[yr] > 0.10 else "")
    print(f"  {yr.year}: {yearly_ret.loc[yr]:>+7.2%}  MDD={yearly_dd.loc[yr]:>6.2%}{marker}")
print(f"  正收益年: {(yearly_ret>0).sum()}/{len(yearly_ret)}")

# ============================================================
# PART B: SMA 窗口信号时效性分析
# ============================================================
print("\n\n" + "=" * 120)
print("  PART B: SMA 窗口信号时效性分析")
print("=" * 120)

windows = [20, 30, 50, 60, 75, 100, 120, 150]

events = {
    '2015股灾':  ('2015-01-01', '2015-12-31', '2015-06-12'),
    '2016熔断':  ('2015-12-01', '2016-02-29', '2016-01-04'),
    '2018熊市':  ('2017-12-01', '2019-01-31', '2018-01-24'),
    '2020疫情':  ('2019-12-01', '2020-06-30', '2020-02-19'),
    '2022双杀':  ('2021-12-01', '2022-12-31', '2022-01-04'),
    '2024雪球':  ('2023-12-01', '2024-04-30', '2024-01-02'),
}

sma_cache = {w: hs300.rolling(w).mean() for w in windows}


def event_analysis(price, sma, event_name, peak_str, start, end):
    """返回 (first_cross_date, drawdown_at_signal, delay_days, below_days)"""
    sub = price[start:end]
    sub_sma = sma.reindex(sub.index).ffill()
    below = (sub < sub_sma).astype(int)
    confirmed = (below.rolling(3).sum() >= 3)
    peak_dt = pd.Timestamp(peak_str)

    post = confirmed[peak_dt:]
    cd = post[post].index
    if len(cd) == 0:
        post_s = below[peak_dt:]
        cd = post_s[post_s == 1].index
    if len(cd) == 0:
        return None, None, None, 0

    first = cd[0]
    pv = sub.loc[peak_dt] if peak_dt in sub.index else sub.max()
    sv = price.loc[first]
    return first, sv / pv - 1, (first - peak_dt).days, below.sum()


def false_signals(price, sma):
    """假信号: 跌破SMA 10日内收回且跌幅<=5%"""
    below = (price < sma).astype(int)
    entry = ((below.diff() == 1) & (below == 1))
    crisis = [('2015-06-01', '2016-03-01'), ('2018-01-01', '2019-01-31'),
              ('2020-02-01', '2020-04-30'), ('2022-01-01', '2022-12-31')]
    total = 0
    clean = 0
    for d in entry[entry].index:
        loc = price.index.get_loc(d)
        fut = price.iloc[loc:loc+20]
        fsma = sma.reindex(fut.index).ffill()
        if len(fut) < 3:
            continue
        still = (fut < fsma).astype(int)
        rec = still[still == 0].index
        if len(rec) > 0 and (rec[0] - d).days <= 14:
            pd_ = fut[:rec[0]]
            if (pd_ / pd_.iloc[0] - 1).min() > -0.05:
                total += 1
                in_crisis = any(pd.Timestamp(cs) <= d <= pd.Timestamp(ce) for cs, ce in crisis)
                if not in_crisis:
                    clean += 1
    return total, clean


header = f"{'SMA':>6}"
for ev_name in events:
    header += f" | {ev_name:>14}"
header += f" | {'假信号':>7} | {'评估':>12}"
print(f"\n{header}")
print("-" * len(header))

best_score = -999
best_w = None
score_by_w = {}

for w in windows:
    row = f"  SMA{w:>3d}  "
    score = 0
    for ev_name, (s, e, p) in events.items():
        cd, dd, delay, bd = event_analysis(hs300, sma_cache[w], ev_name, p, s, e)
        if cd is None:
            row += f" | {'未触发':>14}"
            score -= 1
        elif dd is None or dd > -0.02:
            row += f" | {'峰值前':>14}"
            score += 3
        else:
            if dd > -0.05:
                m, sc = "!!", 3
            elif dd > -0.10:
                m, sc = "ok", 2
            elif dd > -0.15:
                m, sc = "慢", 1
            elif dd > -0.20:
                m, sc = "太慢", 0
            else:
                m, sc = "失败", -1
            score += sc
            row += f" | {dd:>+7.1%} {delay:>2d}d {m:>2}"

    fa, fc = false_signals(hs300, sma_cache[w])
    fa_year = fc / N_YEARS
    score -= fa_year  # 每个假信号扣1分

    row += f" | {fa_year:>5.1f}/年"
    if w <= 30:
        ev = "太快假信号多"
    elif w <= 50:
        ev = "偏快" if fa_year > 1.5 else "快但可用"
    elif w <= 75:
        ev = "平衡好" if fa_year <= 1.5 else "偏慢"
    elif w <= 100:
        ev = "稳健偏慢"
    else:
        ev = "太慢错过急跌"
    row += f" | {ev:>12}"
    print(row)
    score_by_w[w] = score
    if score > best_score:
        best_score = score
        best_w = w

# 2015 深度分析
print(f"\n\n{'='*80}")
print(f"  深度聚焦: 2015 股灾")
print(f"{'='*80}")

h2015 = hs300['2015-01-01':'2015-12-31']
pk = h2015.idxmax()
pk_v = h2015.max()
tr = h2015.idxmin()
tr_v = h2015.min()
print(f"  峰值: {pk.date()} @ {pk_v:.0f}")
print(f"  谷底: {tr.date()} @ {tr_v:.0f}")
print(f"  总跌幅: {tr_v/pk_v-1:.1%}")
print(f"  下跌天数: {len(h2015[pk:tr])} 交易日")

print(f"\n  {'SMA':>5} | {'信号日':>12} | {'时跌幅':>8} | {'延迟':>7} | {'HS300':>8} | {'剩余跌幅':>8}")
print(f"  -----+--------------+----------+---------+----------+---------")
for w in windows:
    sma = sma_cache[w].reindex(h2015.index).ffill()
    below = (h2015 < sma).astype(int)
    conf = (below.rolling(3).sum() >= 3)
    post = conf[pk:]
    cd = post[post].index
    if len(cd) == 0:
        cd = below[pk:][below[pk:] == 1].index
    if len(cd) > 0:
        f = cd[0]
        sv = hs300.loc[f]
        dd = sv / pk_v - 1
        rem = tr_v / sv - 1
        print(f"  SMA{w:>3d} | {f.date()} | {dd:>+7.1%} | {(f.date()-pk.date()).days:>3d}d | {sv:>7.0f} | {rem:>+7.1%}")
    else:
        print(f"  SMA{w:>3d} | {'未触发':>12} |")

# 推荐
print(f"\n\n{'='*80}")
print("  综合推荐")
print("=" * 80)

print(f"""
  评分机制: 早期信号(<-5%触发)+3, 正常信号(<-10%)+2, 慢信号(<-15%)+1,
            太慢(<-20%)+0, 未触发-1, 假信号每1次/年-1

  各窗口综合得分:""")
for w in sorted(score_by_w, key=lambda x: score_by_w[x], reverse=True):
    marker = " <<<" if w == best_w else ""
    print(f"    SMA{w:>3d}: {score_by_w[w]:>3.0f}{marker}")

print(f"""
  推荐窗口: SMA {best_w}
""")

print("\n分析完成。")
