"""
==========================================================================
KOSDAQ 150 기반 상대 모멘텀 + 추세 추종 백테스트
==========================================================================
전략 요약:
  - 유니버스: KOSDAQ 150 주요 종목 (현재 구성 기준, 생존 편향 주의)
  - 데이터: 최근 3개년 (yfinance, .KQ 종목)
  - 비교 대상: 코스닥 지수 (^KQ11)
  - 매월 말 6개월 모멘텀 상위 10개 후보 선정
  - 진입: 20일 신고가 + 골든크로스(MA20>MA60) + ADX(14)>=25 (익일 시가)
  - 청산: 데드크로스 OR -5% 손절 (익일 시가)
  - 재진입: 손절 후 새 골든크로스 발생 전까지 금지
  - 포트폴리오: 종목당 10%, 비어있는 슬롯은 현금(수익률 0%)
  - 비용: 왕복 0.3% (코스닥 거래세 + 수수료, 코스피보다 높음)
  - 한계: 생존 편향, 슬리피지 미반영, 유동성 미고려
==========================================================================
"""

import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams
from datetime import datetime, timedelta

# ------------------------------------------------------------------
# 한글 폰트 설정 (Windows 환경)
# ------------------------------------------------------------------
try:
    rcParams['font.family'] = 'Malgun Gothic'
except Exception:
    pass
rcParams['axes.unicode_minus'] = False

# ==================================================================
# 1. 설정 (Configuration)
# ==================================================================
END_DATE   = datetime(2026, 3, 24)
START_DATE = END_DATE - timedelta(days=365 * 3 + 180)   # 웜업 포함 약 3.5년

KOSDAQ_INDEX_TICKER = "^KQ11"

TOP_K              = 10
MOMENTUM_WINDOW    = 126       # 6개월 모멘텀 (영업일 기준)
MA_SHORT           = 20
MA_LONG            = 60
ADX_PERIOD         = 14
ADX_THRESHOLD      = 25.0
STOP_LOSS          = -0.05     # -5%
POSITION_SIZE      = 0.10      # 10%
TRANSACTION_COST   = 0.003     # 왕복 0.3% (코스닥: 거래세 0.20% + 수수료)

# ------------------------------------------------------------------
# KOSDAQ 150 주요 종목 (2024 기준, 시총 상위권)
# 종목코드.KQ 형식 사용
# ------------------------------------------------------------------
KOSDAQ_TICKERS = [
    "247540.KQ",  # 에코프로비엠
    "086520.KQ",  # 에코프로
    "373220.KQ",  # (참고: LG엔솔은 KS지만 코스닥에 유사종목 보완)
    "068760.KQ",  # 셀트리온제약
    "091990.KQ",  # 셀트리온헬스케어(현 셀트리온)
    "263750.KQ",  # 펄어비스
    "293490.KQ",  # 카카오게임즈
    "112040.KQ",  # 위메이드
    "035900.KQ",  # JYP Ent.
    "041510.KQ",  # SM엔터테인먼트
    "122870.KQ",  # 와이지엔터테인먼트
    "035720.KQ",  # (코스닥 참고)
    "058470.KQ",  # 리노공업
    "045020.KQ",  # 코이즈
    "196170.KQ",  # 알테오젠
    "145020.KQ",  # 휴젤
    "214150.KQ",  # 클래시스
    "357780.KQ",  # 솔브레인
    "232140.KQ",  # 와이씨
    "095340.KQ",  # ISC
    "086900.KQ",  # 메디오젠
    "140410.KQ",  # 메지온
    "091810.KQ",  # 티웨이홀딩스
    "078130.KQ",  # 국일인토트
    "060370.KQ",  # 다원시스
    "041960.KQ",  # 블리자드코리아 (참고 제외 가능)
    "900110.KQ",  # 이스트아시아홀딩스
    "003380.KQ",  # 하림지주
    "017800.KQ",  # 현대엘리베이터
    "039130.KQ",  # 하나투어
    "290510.KQ",  # 레인보우로보틱스
    "048260.KQ",  # 오스템임플란트
    "091480.KQ",  # 이엔플러스
    "066970.KQ",  # 엘앤에프
    "223190.KQ",  # 에스티아이
    "039440.KQ",  # 에스티큐브
    "237690.KQ",  # 에스티팜
    "150120.KQ",  # 에나인더스트리
    "251970.KQ",  # 펌텍코리아
    "024940.KQ",  # PN풍년
    "006910.KQ",  # 코스모화학
    "032750.KQ",  # 삼성카드(참고)
    "199800.KQ",  # 툴젠
    "217270.KQ",  # 넵튠
    "060310.KQ",  # 3S
    "078340.KQ",  # 컴투스
    "063080.KQ",  # 게임빌
    "053800.KQ",  # 안랩
    "067160.KQ",  # 아프리카TV
    "035760.KQ",  # CJ ENM
    "108860.KQ",  # 셀바이오텍
    "086820.KQ",  # 바이넥스
    "900070.KQ",  # 글로벌스탠다드테크놀로지
    "222080.KQ",  # 씨아이에스
    "054040.KQ",  # 한국팩키지
    "043150.KQ",  # 바텍
    "003090.KQ",  # 대웅
    "194480.KQ",  # 데브시스터즈
    "095660.KQ",  # 네오위즈
    "123690.KQ",  # 한독크레아제
    "036810.KQ",  # 에프에스티
]

TICKER_NAME = {
    "247540.KQ": "에코프로비엠",      "086520.KQ": "에코프로",
    "068760.KQ": "셀트리온제약",      "091990.KQ": "셀트리온헬스케어",
    "263750.KQ": "펄어비스",          "293490.KQ": "카카오게임즈",
    "112040.KQ": "위메이드",          "035900.KQ": "JYP Ent.",
    "041510.KQ": "SM엔터",           "122870.KQ": "YG엔터",
    "058470.KQ": "리노공업",          "196170.KQ": "알테오젠",
    "145020.KQ": "휴젤",             "214150.KQ": "클래시스",
    "357780.KQ": "솔브레인",          "066970.KQ": "엘앤에프",
    "078340.KQ": "컴투스",           "063080.KQ": "게임빌",
    "053800.KQ": "안랩",             "067160.KQ": "아프리카TV",
    "035760.KQ": "CJ ENM",          "290510.KQ": "레인보우로보틱스",
    "048260.KQ": "오스템임플란트",     "039130.KQ": "하나투어",
    "095340.KQ": "ISC",              "232140.KQ": "와이씨",
    "237690.KQ": "에스티팜",          "194480.KQ": "데브시스터즈",
    "095660.KQ": "네오위즈",          "043150.KQ": "바텍",
    "373220.KQ": "참고종목",          "086900.KQ": "메디오젠",
    "060370.KQ": "다원시스",          "003380.KQ": "하림지주",
    "291690.KQ": "레인보우로보틱스2",   "223190.KQ": "에스티아이",
    "251970.KQ": "펌텍코리아",        "199800.KQ": "툴젠",
    "217270.KQ": "넵튠",             "060310.KQ": "3S",
    "108860.KQ": "셀바이오텍",        "086820.KQ": "바이넥스",
    "222080.KQ": "씨아이에스",        "043150.KQ": "바텍",
    "036810.KQ": "에프에스티",        "091810.KQ": "티웨이홀딩스",
}


# ==================================================================
# 2. 데이터 다운로드
# ==================================================================
def download_data(tickers, start, end):
    print(f"\n[데이터 다운로드] {len(tickers)}개 종목 + 코스닥 지수 ({start.date()} ~ {end.date()})")

    all_t = tickers + [KOSDAQ_INDEX_TICKER]
    raw = yf.download(
        all_t,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False
    )

    if raw.empty:
        raise ValueError("데이터 다운로드 실패")

    closes = raw["Close"]
    opens  = raw["Open"]
    highs  = raw["High"]
    lows   = raw["Low"]

    kosdaq_close = closes[KOSDAQ_INDEX_TICKER].copy()

    stock_close = closes[tickers].copy()
    stock_open  = opens[tickers].copy()
    stock_high  = highs[tickers].copy()
    stock_low   = lows[tickers].copy()

    valid_ratio   = stock_close.notna().mean()
    valid_tickers = valid_ratio[valid_ratio >= 0.5].index.tolist()
    excluded      = set(tickers) - set(valid_tickers)

    if excluded:
        names = [TICKER_NAME.get(t, t) for t in excluded]
        print(f"  * 데이터 부족 제외 ({len(excluded)}개): {names}")

    print(f"  [OK] 유효 종목: {len(valid_tickers)}개 | 코스닥 지수: {kosdaq_close.notna().sum()}일")
    return (
        stock_close[valid_tickers],
        stock_open[valid_tickers],
        stock_high[valid_tickers],
        stock_low[valid_tickers],
        kosdaq_close,
        valid_tickers,
    )


# ==================================================================
# 3. Welles Wilder ADX 계산
# ==================================================================
def calc_welles_wilder_adx(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low

    pos_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move.values, 0.0),
        index=close.index)
    neg_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move.values, 0.0),
        index=close.index)

    def wilder_smooth(series, p):
        result = np.full(len(series), np.nan)
        vals   = series.values
        start  = p - 1
        while start < len(vals) and np.isnan(vals[start]):
            start += 1
        if start + p > len(vals):
            return pd.Series(result, index=series.index)
        result[start + p - 1] = np.nansum(vals[start:start + p])
        for i in range(start + p, len(vals)):
            prev_val = result[i - 1]
            cur_val  = vals[i]
            if not np.isnan(prev_val):
                result[i] = prev_val - (prev_val / p) + (cur_val if not np.isnan(cur_val) else 0)
        return pd.Series(result, index=series.index)

    atr    = wilder_smooth(tr,     period)
    pdm    = wilder_smooth(pos_dm, period)
    ndm    = wilder_smooth(neg_dm, period)

    pdi    = 100 * pdm / atr
    ndi    = 100 * ndm / atr
    di_sum = pdi + ndi
    dx     = pd.Series(
        np.where(di_sum != 0, 100 * (pdi - ndi).abs().values / di_sum.values, 0.0),
        index=close.index)

    adx = wilder_smooth(dx, period)
    return pd.Series(adx, index=close.index)


def compute_indicators(close, open_, high, low):
    ma20   = close.rolling(MA_SHORT).mean()
    ma60   = close.rolling(MA_LONG).mean()
    high20 = close.rolling(MA_SHORT).max()

    adx_dict = {}
    print("  ADX 계산 (Welles Wilder)...", end="", flush=True)
    tickers = close.columns.tolist()
    for i, t in enumerate(tickers):
        if i % 10 == 0:
            print(f" {i+1}/{len(tickers)}", end="", flush=True)
        try:
            adx_dict[t] = calc_welles_wilder_adx(high[t], low[t], close[t], ADX_PERIOD)
        except Exception:
            adx_dict[t] = pd.Series(np.nan, index=close.index)
    print(" [OK]")

    adx_5ma = pd.DataFrame(adx_dict).rolling(5).mean()
    return ma20, ma60, high20, adx_5ma


# ==================================================================
# 4. 백테스트 실행
# ==================================================================
def run_backtest(valid_tickers, close, open_, high, low, ma20, ma60, high20, adx_5ma):
    backtest_start = END_DATE - timedelta(days=365 * 3)
    dates    = close.index
    bt_dates = dates[dates >= pd.Timestamp(backtest_start)]

    print(f"\n[백테스트 실행] {bt_dates[0].date()} ~ {bt_dates[-1].date()} ({len(bt_dates)}일)")

    positions         = {}   # ticker -> {entry_price, entry_date}
    banned            = {}   # ticker -> bool (손절 후 금지)
    daily_rets        = []
    trade_log         = []
    momentum_candidates = []
    last_rebal_month  = None

    for i, today in enumerate(bt_dates):
        if i == 0:
            daily_rets.append(0.0)
            continue
        prev = bt_dates[i - 1]

        # ---- 월 리밸런싱 ----
        if today.month != prev.month or last_rebal_month is None:
            six_mo_ago = today - timedelta(days=MOMENTUM_WINDOW)
            past_idx   = dates[dates <= six_mo_ago]
            if len(past_idx) > 0:
                ref_date = past_idx[-1]
                ret_6m   = {}
                for t in valid_tickers:
                    try:
                        p_now = close.loc[prev, t]
                        p_ref = close.loc[ref_date, t]
                        if pd.notna(p_now) and pd.notna(p_ref) and p_ref > 0:
                            ret_6m[t] = p_now / p_ref - 1
                    except KeyError:
                        pass
                if ret_6m:
                    momentum_candidates = sorted(ret_6m, key=lambda x: ret_6m[x], reverse=True)[:TOP_K]
                    last_rebal_month    = today.month

        # ---- 재진입 금지 해제 (골든크로스) ----
        prev2 = bt_dates[i - 2] if i >= 2 else None
        if prev2 is not None:
            for t in list(banned.keys()):
                if banned.get(t, False):
                    try:
                        was_below = ma20.loc[prev2, t] <= ma60.loc[prev2, t]
                        is_above  = ma20.loc[prev, t]  >  ma60.loc[prev, t]
                        if was_below and is_above:
                            banned[t] = False
                    except (KeyError, TypeError):
                        pass

        # ---- 진입 신호 (어제 종가 기반, 오늘 시가 체결) ----
        new_entries = []
        for t in momentum_candidates:
            if t in positions or banned.get(t, False):
                continue
            if len(positions) >= TOP_K:
                break
            try:
                c_prev       = close.loc[prev, t]
                h20_prev     = high20.loc[prev, t]
                ma20_prev    = ma20.loc[prev, t]
                ma60_prev    = ma60.loc[prev, t]
                adx_prev     = adx_5ma.loc[prev, t]
                open_today   = open_.loc[today, t]

                if any(pd.isna(v) for v in [c_prev, h20_prev, ma20_prev, ma60_prev, adx_prev, open_today]):
                    continue
                if open_today <= 0:
                    continue

                if (c_prev >= h20_prev) and (ma20_prev > ma60_prev) and (adx_prev >= ADX_THRESHOLD):
                    positions[t] = {'entry_price': open_today, 'entry_date': today}
                    banned[t]    = False
                    new_entries.append(t)
            except (KeyError, TypeError):
                continue

        # ---- 청산 신호 ----
        exits = []
        for t in list(positions.keys()):
            try:
                ma20_prev  = ma20.loc[prev, t]
                ma60_prev  = ma60.loc[prev, t]
                open_today = open_.loc[today, t]
                entry_p    = positions[t]['entry_price']

                if pd.isna(open_today) or open_today <= 0:
                    continue

                dead_cross = False
                if prev2 is not None:
                    try:
                        was_above  = ma20.loc[prev2, t] >  ma60.loc[prev2, t]
                        is_below   = ma20_prev <= ma60_prev
                        dead_cross = was_above and is_below
                    except (KeyError, TypeError):
                        pass

                stop_hit = (open_today / entry_p - 1) <= STOP_LOSS
                if dead_cross or stop_hit:
                    exits.append((t, open_today, stop_hit))
            except (KeyError, TypeError):
                continue

        for t, exit_price, is_stop in exits:
            entry_p = positions[t]['entry_price']
            trade_log.append({
                'ticker':      t,
                'name':        TICKER_NAME.get(t, t),
                'entry_date':  positions[t]['entry_date'],
                'exit_date':   today,
                'entry_price': entry_p,
                'exit_price':  exit_price,
                'return':      (exit_price / entry_p) - 1 - TRANSACTION_COST,
                'exit_reason': '손절' if is_stop else '데드크로스',
            })
            if is_stop:
                banned[t] = True
            del positions[t]

        # ---- 일별 수익률 ----
        pos_ret = 0.0
        for t in positions:
            try:
                pc = close.loc[prev, t]
                tc = close.loc[today, t]
                if pd.notna(pc) and pd.notna(tc) and pc > 0:
                    pos_ret += (tc / pc - 1) * POSITION_SIZE
            except (KeyError, TypeError):
                pass
        pos_ret -= len(new_entries) * POSITION_SIZE * (TRANSACTION_COST / 2)
        daily_rets.append(pos_ret)

    return daily_rets, bt_dates, trade_log, positions


# ==================================================================
# 5. 성과 지표 출력
# ==================================================================
def calc_performance(daily_rets, bt_dates, trade_log, positions, close):
    rets      = pd.Series(daily_rets, index=bt_dates)
    cum       = (1 + rets).cumprod()
    roll_max  = cum.expanding().max()
    drawdown  = (cum - roll_max) / roll_max
    mdd       = drawdown.min()
    total_ret = cum.iloc[-1] - 1
    n_years   = len(bt_dates) / 252
    cagr      = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe    = (rets.mean() * 252) / (rets.std() * np.sqrt(252)) if rets.std() > 0 else 0

    if trade_log:
        tl          = pd.DataFrame(trade_log)
        n_trades    = len(tl)
        n_win       = (tl['return'] > 0).sum()
        win_rate    = n_win / n_trades
        avg_ret     = tl['return'].mean()
        wins        = tl.loc[tl['return'] > 0, 'return']
        losses      = tl.loc[tl['return'] <= 0, 'return']
        avg_win     = wins.mean()   if len(wins)   > 0 else 0
        avg_loss    = losses.mean() if len(losses) > 0 else 0
        gp          = wins.sum()    if len(wins)   > 0 else 0
        gl          = losses.sum()  if len(losses) > 0 else 0
        pf          = abs(gp / gl)  if gl != 0 else float('inf')
        avg_pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        n_stop      = (tl['exit_reason'] == '손절').sum()
    else:
        n_trades = n_win = n_stop = 0
        win_rate = avg_ret = avg_win = avg_loss = pf = avg_pl_ratio = 0

    print("\n" + "=" * 60)
    print("  [Stats] 코스닥 150 백테스트 성과 지표")
    print("=" * 60)
    print(f"  기     간  : {bt_dates[0].date()} ~ {bt_dates[-1].date()}")
    print(f"  총 수익률  : {total_ret:+.2%}")
    print(f"  CAGR       : {cagr:+.2%}")
    print(f"  MDD        : {mdd:.2%}")
    print(f"  샤프 비율  : {sharpe:.2f}")
    print(f"  매매 횟수  : {n_trades}회 (손절 {n_stop}회)")
    print(f"  승     률  : {win_rate:.1%} ({n_win}승 {n_trades-n_win}패)")
    print(f"  Profit Factor: {pf:.2f}")
    print(f"  평균 손익비: {avg_pl_ratio:.2f}")
    print(f"  거래당 평균: {avg_ret:+.2%}")
    print("=" * 60)

    print("\n  [Pos] 현재 보유 포지션:")
    if positions:
        for t, info in positions.items():
            try:
                latest  = close[t].dropna().iloc[-1]
                ret_now = (latest / info['entry_price']) - 1
                print(f"    [{TICKER_NAME.get(t, t):<12}] 매수가: {info['entry_price']:>8,.0f}  "
                      f"현재가: {latest:>8,.0f}  수익률: {ret_now:+.2%}  매수일: {info['entry_date'].date()}")
            except Exception:
                print(f"    [{TICKER_NAME.get(t, t)}]  매수일: {info['entry_date'].date()}")
    else:
        print("    현재 보유 종목 없음")

    return cum, drawdown, rets


# ==================================================================
# 6. 현재 신호 스캔
# ==================================================================
def scan_current_signals(valid_tickers, close, open_, high, low,
                         ma20, ma60, high20, adx_5ma, positions):
    last_date = close.index[-1]
    six_mo_ago = last_date - timedelta(days=MOMENTUM_WINDOW)
    past_idx   = close.index[close.index <= six_mo_ago]
    if len(past_idx) == 0:
        print("\n  [!] 모멘텀 계산용 과거 데이터 부족")
        return

    ref_date = past_idx[-1]
    signals  = []
    for t in valid_tickers:
        try:
            c_now    = close.loc[last_date, t]
            c_ref    = close.loc[ref_date, t]
            h20      = high20.loc[last_date, t]
            ma20_now = ma20.loc[last_date, t]
            ma60_now = ma60.loc[last_date, t]
            adx_now  = adx_5ma.loc[last_date, t]

            if any(pd.isna(v) for v in [c_now, c_ref, h20, ma20_now, ma60_now, adx_now]):
                continue
            if c_ref <= 0:
                continue

            mom_6m    = c_now / c_ref - 1
            cond_b    = c_now >= h20
            cond_g    = ma20_now > ma60_now
            cond_adx  = adx_now >= ADX_THRESHOLD
            all_ok    = cond_b and cond_g and cond_adx

            signals.append({
                'ticker':   t,
                'name':     TICKER_NAME.get(t, t),
                'mom_6m':   mom_6m,
                'breakout': cond_b,
                'golden':   cond_g,
                'adx':      adx_now,
                'all':      all_ok,
                'holding':  t in positions,
                'close':    c_now,
            })
        except (KeyError, TypeError):
            continue

    if not signals:
        print("\n  [!] 유효한 신호 없음")
        return

    df = pd.DataFrame(signals).sort_values('mom_6m', ascending=False)

    print("\n" + "=" * 70)
    print(f"  [Scan] 코스닥 현재 신호 스캔  (기준일: {last_date.date()})")
    print("=" * 70)
    print(f"  {'순위':>4}  {'종목명':<14} {'6M수익':>8} {'ADX':>6} {'신고가':>6} {'MA정배열':>8} {'전략신호':>8} {'상태':>6}")
    print("-" * 70)
    for rank, (_, row) in enumerate(df.head(20).iterrows(), 1):
        sig  = "[OK]ALL" if row['all'] else ("[~]일부" if (row['golden'] or row['breakout']) else "[X]")
        hold = "보유중" if row['holding'] else ("진입가능" if row['all'] else "-")
        print(f"  {rank:>4}  {row['name']:<14} {row['mom_6m']:>+7.1%} {row['adx']:>6.1f} "
              f"  {'O' if row['breakout'] else 'X':>5}   {'O' if row['golden'] else 'X':>5}  {sig:>8} {hold:>6}")

    entry_df = df[df['all']].head(10)
    print("\n" + "=" * 70)
    print("  [Entry] 전략 ALL 조건 충족 — 코스닥 신규 진입 후보")
    print("=" * 70)
    if len(entry_df) == 0:
        print("  현재 조건 충족 종목 없음")
    else:
        for rank, (_, row) in enumerate(entry_df.iterrows(), 1):
            status = "보유중" if row['holding'] else "[*] 신규진입"
            print(f"  {rank:>2}. {row['name']:<14}  현재가: {row['close']:>8,.0f}원  "
                  f"6M: {row['mom_6m']:>+6.1%}  ADX: {row['adx']:.1f}  {status}")


# ==================================================================
# 7. 코스피 vs 코스닥 전략 비교 분석 출력
# ==================================================================
def print_market_comparison():
    print("\n" + "=" * 70)
    print("  [분석] 코스피 vs 코스닥 — 동일 전략 유효성 비교")
    print("=" * 70)
    print("""
  ┌──────────────────┬────────────────────┬────────────────────┐
  │ 구분             │ 코스피 전략         │ 코스닥 전략         │
  ├──────────────────┼────────────────────┼────────────────────┤
  │ 거래비용         │ 왕복 0.2%          │ 왕복 0.3%          │
  │ 변동성           │ 낮음 (대형주)       │ 높음 (중소형주)     │
  │ 유동성           │ 우수               │ 종목별 편차 큼      │
  │ ADX 반응속도     │ 느리고 안정적       │ 빠르고 잦은 신호    │
  │ 손절 빈도        │ 상대적으로 낮음     │ 상대적으로 높음     │
  │ 모멘텀 지속성    │ 6~12개월 비교적     │ 3~6개월로 짧을 수   │
  │                  │ 지속 가능           │ 있음               │
  └──────────────────┴────────────────────┴────────────────────┘

  코스닥 전략 주요 고려사항:
  1) 고변동성으로 인해 ADX 25 조건이 더 자주 충족될 수 있으나,
     단기 급등 후 빠른 되돌림 리스크가 존재합니다.
  2) 손절(-5%) 기준이 코스닥 일반 변동폭에 근접하므로, 불필요한
     손절이 늘어날 수 있어 -7~8% 조정도 고려 가능합니다.
  3) 거래세(코스닥 0.20% vs 코스피 0.18%)와 유동성 부족에 의한
     슬리피지가 실전 수익률을 추가 하락시킬 수 있습니다.
  4) 코스닥 지수 ETF(KODEX 코스닥150) 대비 초과수익 여부가
     전략 유효성의 핵심 판단 기준입니다.
""")


# ==================================================================
# 8. 시각화
# ==================================================================
def plot_results(cum_strat, drawdown, kosdaq_close, bt_dates, trade_log):
    kosdaq_bt  = kosdaq_close.reindex(bt_dates).ffill()
    kosdaq_cum = kosdaq_bt / kosdaq_bt.iloc[0]

    fig, axes = plt.subplots(3, 1, figsize=(14, 12),
                             gridspec_kw={'height_ratios': [3, 1.5, 1], 'hspace': 0.04})
    ax1, ax2, ax3 = axes

    # 누적 수익률
    ax1.plot(cum_strat.index, cum_strat.values * 100 - 100,
             color='#00BCD4', linewidth=2, label='코스닥 전략')
    ax1.plot(kosdaq_cum.index, (kosdaq_cum.values - 1) * 100,
             color='#FF5722', linewidth=1.5, linestyle='--', label='코스닥 Buy&Hold')
    ax1.axhline(0, color='gray', linewidth=0.7, linestyle=':')
    ax1.set_ylabel('누적 수익률 (%)', fontsize=11)
    ax1.set_title('KOSDAQ 150 상대 모멘텀 + 추세 추종 전략 vs 코스닥 지수', fontsize=14, pad=12)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.tick_params(labelbottom=False)

    final_s = cum_strat.iloc[-1] * 100 - 100
    final_k = (kosdaq_cum.iloc[-1] - 1) * 100
    ax1.annotate(f'전략: {final_s:+.1f}%',
                 xy=(cum_strat.index[-1], final_s),
                 xytext=(-90, 10), textcoords='offset points',
                 fontsize=9, color='#00BCD4',
                 arrowprops=dict(arrowstyle='->', color='#00BCD4'))
    ax1.annotate(f'코스닥: {final_k:+.1f}%',
                 xy=(kosdaq_cum.index[-1], final_k),
                 xytext=(-90, -22), textcoords='offset points',
                 fontsize=9, color='#FF5722',
                 arrowprops=dict(arrowstyle='->', color='#FF5722'))

    # MDD
    ax2.fill_between(drawdown.index, drawdown.values * 100, 0,
                     color='#E91E63', alpha=0.4, label='MDD')
    ax2.plot(drawdown.index, drawdown.values * 100, color='#E91E63', linewidth=1)
    ax2.set_ylabel('Drawdown (%)', fontsize=10)
    ax2.legend(loc='lower left', fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.tick_params(labelbottom=False)

    # 보유 종목 수
    if trade_log:
        pos_count = pd.Series(0, index=bt_dates)
        for _, row in pd.DataFrame(trade_log).iterrows():
            mask = (pos_count.index >= row['entry_date']) & (pos_count.index < row['exit_date'])
            pos_count[mask] += 1
        ax3.fill_between(pos_count.index, pos_count.values,
                         color='#673AB7', alpha=0.5, label='보유 종목 수')
        ax3.axhline(TOP_K, color='purple', linestyle='--', linewidth=0.8, alpha=0.6)
        ax3.set_ylim(0, TOP_K + 2)
        ax3.set_ylabel('보유 종목', fontsize=10)
        ax3.legend(loc='upper right', fontsize=9)
    else:
        ax3.text(0.5, 0.5, '거래 없음', transform=ax3.transAxes, ha='center')

    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=30, ha='right')

    plt.tight_layout()
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_kosdaq_result.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"\n  [Chart] 차트 저장: {save_path}")
    plt.show()
    return save_path


# ==================================================================
# 9. 한계점
# ==================================================================
def print_limitations():
    print("\n" + "=" * 60)
    print("  [!] 분석 한계점 및 주의사항 (코스닥)")
    print("=" * 60)
    print("""
  1. [생존 편향] 현재 코스닥 150 구성 종목 기준으로, 백테스트
     기간 중 상장폐지·편출 종목은 미포함 (성과 과대평가 위험).

  2. [거래비용] 왕복 0.3%(수수료+거래세)를 반영했으나, 코스닥
     소형주의 시장충격(Market Impact)과 슬리피지는 미반영.

  3. [손절 기준] -5%는 코스닥 일일 변동폭(±5~10%)에 근접하여
     과도한 손절이 발생할 수 있음. 실전에서는 -7~8% 검토 필요.

  4. [Look-ahead Bias] 신호: t종가 / 체결: t+1시가로 분리.

  5. [ADX 신뢰도] 코스닥 고변동성 환경에서 ADX는 잦은 신호
     변화를 보일 수 있어 'ADX 5일 이동평균' 방식으로 안정화.

  6. [데이터 품질] 일부 코스닥 종목은 yfinance에서 불완전한
     데이터를 제공할 수 있으며, 자동으로 제외 처리됨.

  * 본 결과는 과거 데이터 기반 참고용이며, 미래 수익을 보장하지 않습니다.
""")


# ==================================================================
# 10. 메인 실행
# ==================================================================
def main():
    print("=" * 60)
    print("  KOSDAQ 150 상대 모멘텀 + 추세 추종 백테스트")
    print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 데이터 다운로드
    (stock_close, stock_open, stock_high, stock_low,
     kosdaq_close, valid_tickers) = download_data(KOSDAQ_TICKERS, START_DATE, END_DATE)

    # 2. 지표 계산
    print("\n[지표 계산 중...]")
    ma20, ma60, high20, adx_5ma = compute_indicators(stock_close, stock_open, stock_high, stock_low)

    # 3. 백테스트 실행
    daily_rets, bt_dates, trade_log, positions = run_backtest(
        valid_tickers, stock_close, stock_open, stock_high, stock_low,
        ma20, ma60, high20, adx_5ma
    )

    # 4. 성과 지표
    cum_strat, drawdown, rets = calc_performance(
        daily_rets, bt_dates, trade_log, positions, stock_close
    )

    # 5. 현재 신호 스캔
    scan_current_signals(
        valid_tickers, stock_close, stock_open, stock_high, stock_low,
        ma20, ma60, high20, adx_5ma, positions
    )

    # 6. 거래 내역 출력
    if trade_log:
        tl = pd.DataFrame(trade_log).sort_values('return', ascending=False)
        print("\n  [Log] 완료 거래 내역 — 수익률 상위 10")
        print("-" * 65)
        print(f"  {'종목':<14} {'매수일':>12} {'매도일':>12} {'수익률':>8} {'청산':>8}")
        print("-" * 65)
        for _, r in tl.head(10).iterrows():
            print(f"  {r['name']:<14} {str(r['entry_date'].date()):>12} "
                  f"{str(r['exit_date'].date()):>12} {r['return']:>+7.2%} {r['exit_reason']:>8}")
        print("-" * 65)
        stops = tl[tl['exit_reason'] == '손절']
        print(f"\n  [손절 거래 요약] 총 {len(stops)}회")
        for _, r in stops.iterrows():
            print(f"    {r['name']:<14} {str(r['entry_date'].date()):>12} "
                  f"{str(r['exit_date'].date()):>12} {r['return']:>+7.2%}")

    # 7. 시각화
    plot_results(cum_strat, drawdown, kosdaq_close, bt_dates, trade_log)

    # 8. 비교 분석
    print_market_comparison()

    # 9. 한계점
    print_limitations()


if __name__ == "__main__":
    main()
