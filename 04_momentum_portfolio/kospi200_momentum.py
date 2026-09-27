"""
==========================================================================
KOSPI 200 기반 상대 모멘텀 + 추세 추종 백테스트 (메모리 최적화 버전)
==========================================================================
전략 요약:
  - 유니버스: KOSPI 200 시총 상위 50개 종목 (현재 구성 기준, 생존 편향 주의)
  - 데이터: 최근 3개년 (yfinance)
  - 매월 말 6개월 모멘텀 상위 10개 후보 선정
  - 진입: 20일 신고가 + 골든크로스(MA20>MA60) + ADX(14)>=25 (익일 시가)
  - 청산: 데드크로스 OR -5% 손절 (익일 시가)
  - 재진입: 손절 후 새 골든크로스 발생 전까지 금지
  - 포트폴리오: 종목당 10%, 비어있는 슬롯은 현금(수익률 0%)
  - 비용: 왕복 0.2% (수수료 + 세금)
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
import time
from datetime import datetime, timedelta

# ------------------------------------------------------------------
# 한글 폰트 설정 (Windows 환경)
# ------------------------------------------------------------------
try:
    rcParams['font.family'] = 'Malgun Gothic'
except:
    try:
        rcParams['font.family'] = 'AppleGothic'
    except:
        pass
rcParams['axes.unicode_minus'] = False

# ==================================================================
# 1. 설정 (Configuration)
# ==================================================================
END_DATE   = datetime(2026, 3, 24)   # 현재 날짜
START_DATE = END_DATE - timedelta(days=365 * 3 + 180)  # 3년 + 6개월 웜업

KOSPI_INDEX_TICKER = "^KS11"   # 코스피 지수
N_STOCKS           = 50        # 유니버스 크기 (시총 상위 50개)
TOP_K              = 10        # 모멘텀 상위 선택 종목 수
MOMENTUM_WINDOW    = 126       # 6개월 모멘텀 (영업일 기준)
MA_SHORT           = 20        # 단기 이동평균
MA_LONG            = 60        # 장기 이동평균
ADX_PERIOD         = 14        # ADX 계산 기간
ADX_THRESHOLD      = 25.0      # ADX 최소 임계값
STOP_LOSS          = -0.05     # 손절 기준 (-5%)
POSITION_SIZE      = 0.10      # 종목당 비중 (10%)
TRANSACTION_COST   = 0.002     # 왕복 거래비용 (0.2%)

# ------------------------------------------------------------------
# KOSPI 200 시총 상위 ~50개 종목 (2024 기준 수동 선정)
# 실제 운용 시 pykrx 등으로 동적 조회 권장
# ------------------------------------------------------------------
KOSPI_TOP50_TICKERS = [
    "005930.KS",  # 삼성전자
    "000660.KS",  # SK하이닉스
    "373220.KS",  # LG에너지솔루션
    "207940.KS",  # 삼성바이오로직스
    "005380.KS",  # 현대차
    "005490.KS",  # POSCO홀딩스
    "068270.KS",  # 셀트리온
    "051910.KS",  # LG화학
    "035420.KS",  # NAVER
    "000270.KS",  # 기아
    "012330.KS",  # 현대모비스
    "028260.KS",  # 삼성물산
    "066570.KS",  # LG전자
    "323410.KS",  # 카카오뱅크
    "035720.KS",  # 카카오
    "003550.KS",  # LG
    "015760.KS",  # 한국전력
    "086790.KS",  # 하나금융지주
    "105560.KS",  # KB금융
    "055550.KS",  # 신한지주
    "032830.KS",  # 삼성생명
    "096770.KS",  # SK이노베이션
    "017670.KS",  # SK텔레콤
    "034730.KS",  # SK
    "003490.KS",  # 대한항공
    "010130.KS",  # 고려아연
    "000810.KS",  # 삼성화재
    "009150.KS",  # 삼성전기
    "018260.KS",  # 삼성에스디에스
    "011170.KS",  # 롯데케미칼
    "033780.KS",  # KT&G
    "030200.KS",  # KT
    "006400.KS",  # 삼성SDI
    "036570.KS",  # 엔씨소프트
    "010950.KS",  # S-Oil
    "251270.KS",  # 넷마블
    "316140.KS",  # 우리금융지주
    "071050.KS",  # 한국금융지주
    "009540.KS",  # HD한국조선해양
    "042660.KS",  # 한화오션
    "329180.KS",  # HD현대중공업
    "000720.KS",  # 현대건설
    "011790.KS",  # SKC
    "047050.KS",  # 포스코인터내셔널
    "086280.KS",  # 현대글로비스
    "097950.KS",  # CJ제일제당
    "003230.KS",  # 삼양식품
    "024110.KS",  # 기업은행
    "139480.KS",  # 이마트
    "282330.KS",  # BGF리테일
]

TICKER_NAME = {
    "005930.KS": "삼성전자",     "000660.KS": "SK하이닉스",
    "373220.KS": "LG에너지솔루션", "207940.KS": "삼성바이오로직스",
    "005380.KS": "현대차",       "005490.KS": "POSCO홀딩스",
    "068270.KS": "셀트리온",     "051910.KS": "LG화학",
    "035420.KS": "NAVER",       "000270.KS": "기아",
    "012330.KS": "현대모비스",   "028260.KS": "삼성물산",
    "066570.KS": "LG전자",       "323410.KS": "카카오뱅크",
    "035720.KS": "카카오",       "003550.KS": "LG",
    "015760.KS": "한국전력",     "086790.KS": "하나금융지주",
    "105560.KS": "KB금융",       "055550.KS": "신한지주",
    "032830.KS": "삼성생명",     "096770.KS": "SK이노베이션",
    "017670.KS": "SK텔레콤",     "034730.KS": "SK",
    "003490.KS": "대한항공",     "010130.KS": "고려아연",
    "000810.KS": "삼성화재",     "009150.KS": "삼성전기",
    "018260.KS": "삼성에스디에스", "011170.KS": "롯데케미칼",
    "033780.KS": "KT&G",         "030200.KS": "KT",
    "006400.KS": "삼성SDI",      "036570.KS": "엔씨소프트",
    "010950.KS": "S-Oil",        "251270.KS": "넷마블",
    "316140.KS": "우리금융지주", "071050.KS": "한국금융지주",
    "009540.KS": "HD한국조선해양", "042660.KS": "한화오션",
    "329180.KS": "HD현대중공업",  "000720.KS": "현대건설",
    "011790.KS": "SKC",          "047050.KS": "포스코인터내셔널",
    "086280.KS": "현대글로비스",  "097950.KS": "CJ제일제당",
    "003230.KS": "삼양식품",     "024110.KS": "기업은행",
    "139480.KS": "이마트",       "282330.KS": "BGF리테일",
}


# ==================================================================
# 2. 데이터 다운로드
# ==================================================================
def download_data(tickers, start, end):
    """yfinance로 OHLC 데이터 일괄 다운로드."""
    print(f"\n[데이터 다운로드] {len(tickers)}개 종목 + 코스피 지수 ({start.date()} ~ {end.date()})")
    
    all_tickers = tickers + [KOSPI_INDEX_TICKER]
    
    raw = yf.download(
        all_tickers,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False
    )
    
    if raw.empty:
        raise ValueError("데이터 다운로드 실패: 빈 데이터프레임 반환")
    
    # MultiIndex → dict of (Open, High, Low, Close)
    closes = raw["Close"].copy()
    opens  = raw["Open"].copy()
    highs  = raw["High"].copy()
    lows   = raw["Low"].copy()
    
    # 코스피 지수 분리
    kospi_close = closes[KOSPI_INDEX_TICKER].copy()
    kospi_open  = opens[KOSPI_INDEX_TICKER].copy()
    
    # 종목 데이터만 추출 (기간 중 50% 이상 결측이면 제외)
    stock_close = closes[tickers].copy()
    stock_open  = opens[tickers].copy()
    stock_high  = highs[tickers].copy()
    stock_low   = lows[tickers].copy()
    
    valid_ratio = stock_close.notna().mean()
    valid_tickers = valid_ratio[valid_ratio >= 0.5].index.tolist()
    excluded = set(tickers) - set(valid_tickers)
    
    if excluded:
        print(f"  * 데이터 부족으로 제외된 종목 ({len(excluded)}개): {[TICKER_NAME.get(t, t) for t in excluded]}")
    
    print(f"  [OK] 유효 종목: {len(valid_tickers)}개 | 코스피 지수: {kospi_close.notna().sum()}일")
    
    return (
        stock_close[valid_tickers],
        stock_open[valid_tickers],
        stock_high[valid_tickers],
        stock_low[valid_tickers],
        kospi_close,
        kospi_open,
        valid_tickers,
    )


# ==================================================================
# 3. 기술적 지표 계산
# ==================================================================
def calc_welles_wilder_adx(high, low, close, period=14):
    """
    Welles Wilder 방식 ADX 계산 (RMA/Wilder Smoothing 사용).
    일반 EMA와 다르게 alpha = 1/period 사용.
    """
    n = len(close)
    
    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    
    # Directional Movement
    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low
    
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    pos_dm_s = pd.Series(pos_dm, index=close.index)
    neg_dm_s = pd.Series(neg_dm, index=close.index)
    
    # Wilder Smoothing (RMA)
    def wilder_smooth(series, period):
        result = np.full(len(series), np.nan)
        vals = series.values
        # 초기값: 첫 period개의 단순 합계
        first_valid = period - 1
        while first_valid < len(vals) and np.isnan(vals[first_valid]):
            first_valid += 1
        if first_valid + period > len(vals):
            return pd.Series(result, index=series.index)
        result[first_valid + period - 1] = np.nansum(vals[first_valid:first_valid + period])
        for i in range(first_valid + period, len(vals)):
            if not np.isnan(vals[i]):
                result[i] = result[i-1] - (result[i-1] / period) + vals[i]
            else:
                result[i] = result[i-1]
        return pd.Series(result, index=series.index)
    
    atr14   = wilder_smooth(tr,       period)
    pos_dm14 = wilder_smooth(pos_dm_s, period)
    neg_dm14 = wilder_smooth(neg_dm_s, period)
    
    # DI+ / DI-
    pos_di = 100 * pos_dm14 / atr14
    neg_di = 100 * neg_dm14 / atr14
    
    # DX
    di_sum  = pos_di + neg_di
    dx = np.where(di_sum != 0, 100 * (pos_di - neg_di).abs() / di_sum, 0.0)
    dx_s = pd.Series(dx, index=close.index)
    
    # ADX = Wilder Smooth of DX
    adx = wilder_smooth(dx_s, period)
    return pd.Series(adx, index=close.index)


def compute_indicators(close, open_, high, low):
    """모든 종목에 대해 지표를 계산하여 dict of DataFrame으로 반환."""
    tickers = close.columns.tolist()
    
    ma20  = close.rolling(MA_SHORT).mean()
    ma60  = close.rolling(MA_LONG).mean()
    high20 = close.rolling(MA_SHORT).max()   # 20일 신고가
    
    adx_dict = {}
    print("  ADX 계산 중 (Welles Wilder 방식)...", end="", flush=True)
    for i, t in enumerate(tickers):
        if i % 10 == 0:
            print(f" {i+1}/{len(tickers)}", end="", flush=True)
        try:
            adx_dict[t] = calc_welles_wilder_adx(high[t], low[t], close[t], ADX_PERIOD)
        except Exception:
            adx_dict[t] = pd.Series(np.nan, index=close.index)
    print(" [OK]")
    
    adx_df = pd.DataFrame(adx_dict)
    
    # 5일 ADX 이동평균 (신호 안정성)
    adx_5ma = adx_df.rolling(5).mean()
    
    return ma20, ma60, high20, adx_5ma


# ==================================================================
# 4. 전략 신호 생성 + 포트폴리오 시뮬레이션
# ==================================================================
def run_backtest(valid_tickers, close, open_, high, low, kospi_close, kospi_open):
    """
    일별 시뮬레이션:
      - 월말 모멘텀 리밸런싱
      - 진입/청산 신호 생성 (t 종가)
      - 다음날 시가(t+1 open)로 실행 (Look-ahead bias 방지)
    """
    print("\n[지표 계산 중...]")
    ma20, ma60, high20, adx_5ma = compute_indicators(close, open_, high, low)
    
    # 3년 실제 백테스트 구간 (웜업 제외)
    backtest_start = END_DATE - timedelta(days=365 * 3)
    dates = close.index
    bt_dates = dates[dates >= pd.Timestamp(backtest_start)]
    
    print(f"\n[백테스트 실행] {bt_dates[0].date()} ~ {bt_dates[-1].date()} ({len(bt_dates)}일)")
    
    # 포트폴리오 상태 초기화
    positions = {}   # ticker -> {'entry_price': float, 'entry_date': date, 'stop_loss_ban': bool}
    banned    = {}   # ticker -> bool (손절 후 재진입 금지)
    daily_rets = []  # 날짜별 전략 수익률
    
    # 거래 기록
    trade_log = []
    
    # 월별 모멘텀 후보 (월말 갱신)
    momentum_candidates = []
    last_rebal_month = None
    
    for i, today in enumerate(bt_dates):
        if i == 0:
            daily_rets.append(0.0)
            continue
        
        prev_date = bt_dates[i - 1]
        
        # ----------------------------------------------------------------
        # [월말 리밸런싱] 후보 종목 갱신
        # ----------------------------------------------------------------
        if today.month != prev_date.month or last_rebal_month is None:
            # 6개월 모멘텀 계산
            six_mo_ago = today - timedelta(days=MOMENTUM_WINDOW)
            past_idx = dates[dates <= six_mo_ago]
            if len(past_idx) > 0:
                ref_date = past_idx[-1]
                ret_6m = {}
                for t in valid_tickers:
                    try:
                        p_now = close.loc[prev_date, t]
                        p_ref = close.loc[ref_date, t]
                        if pd.notna(p_now) and pd.notna(p_ref) and p_ref > 0:
                            ret_6m[t] = (p_now / p_ref) - 1
                    except KeyError:
                        pass
                if ret_6m:
                    sorted_tickers = sorted(ret_6m, key=lambda x: ret_6m[x], reverse=True)
                    momentum_candidates = sorted_tickers[:TOP_K]
                    last_rebal_month = today.month
        
        # ----------------------------------------------------------------
        # [진입 신호] t-1 종가(어제) 기준 → 오늘 시가 매수
        # ----------------------------------------------------------------
        prev = prev_date  # 신호 발생 시점 = 어제 종가
        
        new_entries = []
        for t in momentum_candidates:
            if t in positions:
                continue  # 이미 보유 중
            if banned.get(t, False):
                # 손절 후 재진입 금지: 어제 골든크로스 발생했으면 해제
                try:
                    gc = (ma20.loc[prev, t] > ma60.loc[prev, t]) and \
                         (ma20.loc[prev_date, t] <= ma60.loc[prev_date, t] if i >= 2 else False)
                    # 실제로는 이전 날짜의 이전 날짜와 비교
                    prev2_idx = bt_dates[i - 2] if i >= 2 else None
                    if prev2_idx is not None:
                        was_below = ma20.loc[prev2_idx, t] <= ma60.loc[prev2_idx, t]
                        is_above  = ma20.loc[prev, t] > ma60.loc[prev, t]
                        if was_below and is_above:
                            banned[t] = False  # 새 골든크로스 → 금지 해제
                except (KeyError, TypeError):
                    pass
                if banned.get(t, True):
                    continue
            
            if len(positions) >= TOP_K:
                break  # 최대 10 종목
            
            try:
                c_prev   = close.loc[prev, t]
                h20_prev = high20.loc[prev, t]
                ma20_prev = ma20.loc[prev, t]
                ma60_prev = ma60.loc[prev, t]
                adx_prev  = adx_5ma.loc[prev, t]
                open_today = open_.loc[today, t]
                
                if any(pd.isna(v) for v in [c_prev, h20_prev, ma20_prev, ma60_prev, adx_prev, open_today]):
                    continue
                
                # 진입 조건 (AND)
                # 1) 20일 신고가 돌파: 오늘 종가가 어제까지의 20일 최고가를 상향 돌파
                cond_breakout = c_prev >= h20_prev
                # 2) 골든크로스 (MA20 > MA60)
                cond_golden   = ma20_prev > ma60_prev
                # 3) ADX5MA >= 25
                cond_adx      = adx_prev >= ADX_THRESHOLD
                
                if cond_breakout and cond_golden and cond_adx:
                    if open_today > 0 and not np.isnan(open_today):
                        positions[t] = {
                            'entry_price': open_today,
                            'entry_date':  today,
                        }
                        banned[t] = False
                        new_entries.append(t)
            except (KeyError, TypeError):
                continue
        
        # ----------------------------------------------------------------
        # [청산 신호] t-1 종가(어제) 기준 → 오늘 시가 매도
        # ----------------------------------------------------------------
        exits = []
        for t in list(positions.keys()):
            try:
                ma20_prev  = ma20.loc[prev, t]
                ma60_prev  = ma60.loc[prev, t]
                open_today = open_.loc[today, t]
                entry_p    = positions[t]['entry_price']
                
                if pd.isna(open_today) or open_today <= 0:
                    continue
                
                # 데드크로스 확인 (어제 교차 발생 여부)
                prev2_idx = bt_dates[i - 2] if i >= 2 else None
                dead_cross = False
                if prev2_idx is not None:
                    try:
                        ma20_p2 = ma20.loc[prev2_idx, t]
                        ma60_p2 = ma60.loc[prev2_idx, t]
                        if pd.notna(ma20_p2) and pd.notna(ma60_p2):
                            was_above = ma20_p2 > ma60_p2
                            is_below  = ma20_prev <= ma60_prev
                            dead_cross = was_above and is_below
                    except (KeyError, TypeError):
                        pass
                
                # 손절 조건: 오늘 시가가 매수가 대비 -5% 이하
                stop_hit = (open_today / entry_p - 1) <= STOP_LOSS
                
                if dead_cross or stop_hit:
                    exits.append((t, open_today, stop_hit))
            except (KeyError, TypeError):
                continue
        
        for t, exit_price, is_stop in exits:
            entry_p = positions[t]['entry_price']
            ret_raw = (exit_price / entry_p) - 1 - TRANSACTION_COST
            trade_log.append({
                'ticker':      t,
                'name':        TICKER_NAME.get(t, t),
                'entry_date':  positions[t]['entry_date'],
                'exit_date':   today,
                'entry_price': entry_p,
                'exit_price':  exit_price,
                'return':      ret_raw,
                'exit_reason': '손절' if is_stop else '데드크로스',
            })
            if is_stop:
                banned[t] = True  # 손절 후 재진입 금지
            del positions[t]
        
        # ----------------------------------------------------------------
        # [일별 포트폴리오 수익률 계산]
        # ----------------------------------------------------------------
        pos_ret = 0.0
        n_active = len(positions)
        
        for t, info in positions.items():
            try:
                prev_close_t = close.loc[prev, t]
                today_close_t = close.loc[today, t]
                if pd.notna(prev_close_t) and pd.notna(today_close_t) and prev_close_t > 0:
                    r = (today_close_t / prev_close_t) - 1
                    pos_ret += r * POSITION_SIZE
            except (KeyError, TypeError):
                pass
        
        # 신규 진입 수수료 차감 (매수 비용: 0.1%, 절반)
        pos_ret -= len(new_entries) * POSITION_SIZE * (TRANSACTION_COST / 2)
        
        daily_rets.append(pos_ret)
    
    return daily_rets, bt_dates, trade_log, positions


# ==================================================================
# 5. 성과 지표 계산
# ==================================================================
def calc_performance(daily_rets, bt_dates, trade_log, positions, close):
    """성과 지표 계산 및 출력."""
    
    rets = pd.Series(daily_rets, index=bt_dates)
    cum  = (1 + rets).cumprod()
    
    # MDD
    roll_max = cum.expanding().max()
    drawdown = (cum - roll_max) / roll_max
    mdd = drawdown.min()
    
    # 총 수익률
    total_ret = cum.iloc[-1] - 1
    
    # 연환산 수익률
    n_years = len(bt_dates) / 252
    cagr = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0
    
    # 샤프 비율
    sharpe = (rets.mean() * 252) / (rets.std() * np.sqrt(252)) if rets.std() > 0 else 0
    
    # 거래 통계
    if trade_log:
        tl = pd.DataFrame(trade_log)
        n_trades = len(tl)
        n_win    = (tl['return'] > 0).sum()
        win_rate = n_win / n_trades if n_trades > 0 else 0
        avg_ret  = tl['return'].mean()
        
        wins   = tl.loc[tl['return'] > 0, 'return']
        losses = tl.loc[tl['return'] <= 0, 'return']
        avg_win  = wins.mean()  if len(wins)   > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        
        gross_profit = wins.sum()   if len(wins)   > 0 else 0
        gross_loss   = losses.sum() if len(losses) > 0 else 0
        pf = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')
        
        avg_pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    else:
        n_trades = n_win = 0
        win_rate = avg_ret = avg_win = avg_loss = pf = avg_pl_ratio = 0
    
    print("\n" + "=" * 60)
    print("  [Stats] 성과 지표 요약")
    print("=" * 60)
    print(f"  기 간        : {bt_dates[0].date()} ~ {bt_dates[-1].date()}")
    print(f"  총 수익률    : {total_ret:+.2%}")
    print(f"  연환산(CAGR) : {cagr:+.2%}")
    print(f"  MDD          : {mdd:.2%}")
    print(f"  샤프 비율    : {sharpe:.2f}")
    print(f"  총 매매 횟수 : {n_trades}회")
    print(f"  승 률        : {win_rate:.1%} ({n_win}승 {n_trades - n_win}패)")
    print(f"  Profit Factor: {pf:.2f}")
    print(f"  평균 손익비  : {avg_pl_ratio:.2f}")
    print(f"  평균 수익    : {avg_ret:+.2%} / 거래")
    print("=" * 60)
    
    # 현재 보유 포지션
    print("\n  [Pos] 현재 보유 포지션:")
    if positions:
        for t, info in positions.items():
            try:
                latest = close[t].dropna().iloc[-1]
                ret_now = (latest / info['entry_price']) - 1
                print(f"    [{TICKER_NAME.get(t, t)}] 매수가: {info['entry_price']:,.0f}원 | "
                      f"현재가: {latest:,.0f}원 | 수익률: {ret_now:+.2%} | 매수일: {info['entry_date'].date()}")
            except Exception:
                print(f"    [{TICKER_NAME.get(t, t)}] 매수일: {info['entry_date'].date()}")
    else:
        print("    해당 없음 (현재 보유 포지션 없음)")
    
    return cum, drawdown, rets


# ==================================================================
# 6. 현재 신호 스캔 (실전 리스트)
# ==================================================================
def scan_current_signals(valid_tickers, close, open_, high, low,
                         ma20, ma60, high20, adx_5ma, positions):
    """최신 데이터 기준 신규 진입 후보 TOP 10 출력."""
    
    last_date  = close.index[-1]
    prev2_date = close.index[-2] if len(close.index) >= 2 else last_date
    
    # 6개월 모멘텀
    six_mo_ago = last_date - timedelta(days=MOMENTUM_WINDOW)
    past_idx = close.index[close.index <= six_mo_ago]
    if len(past_idx) == 0:
        print("\n  [!] 모멘텀 계산을 위한 과거 데이터 부족")
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
            
            mom_6m = (c_now / c_ref) - 1
            
            cond_breakout = c_now >= h20
            cond_golden   = ma20_now > ma60_now
            cond_adx      = adx_now  >= ADX_THRESHOLD
            
            all_cond  = cond_breakout and cond_golden and cond_adx
            holding   = t in positions
            
            signals.append({
                'ticker':     t,
                'name':       TICKER_NAME.get(t, t),
                'mom_6m':     mom_6m,
                'breakout':   cond_breakout,
                'golden':     cond_golden,
                'adx':        adx_now,
                'all_signal': all_cond,
                'holding':    holding,
                'close':      c_now,
            })
        except (KeyError, TypeError):
            continue
    
    if not signals:
        print("\n  [!] 유효 신호 없음")
        return
    
    df = pd.DataFrame(signals).sort_values('mom_6m', ascending=False)
    
    print("\n" + "=" * 70)
    print("  [Scan] 현재 신호 스캔 — 모멘텀 상위 종목 (최신 기준)")
    print(f"  기준일: {last_date.date()}")
    print("=" * 70)
    print(f"  {'순위':>4}  {'종목명':<16} {'6M수익':>8} {'ADX':>6} {'신고가':>6} {'MA정배열':>8} {'전략신호':>9} {'상태':>6}")
    print("-" * 70)
    
    rank = 1
    for _, row in df.head(20).iterrows():
        sig_str  = "[OK] ALL" if row['all_signal'] else ("[~] 일부" if (row['golden'] or row['breakout']) else "[X]")
        hold_str = "보유중" if row['holding'] else ("진입가능" if row['all_signal'] else "-")
        break_s   = "O" if row['breakout'] else "X"
        golden_s  = "O" if row['golden']   else "X"
        
        print(f"  {rank:>4}  {row['name']:<16} {row['mom_6m']:>+7.1%} {row['adx']:>6.1f} "
              f"{'신고가':>4}:{break_s} {'MA':>2}:{golden_s} {sig_str:>9} {hold_str:>6}")
        rank += 1
    
    entry_list = df[df['all_signal']].head(10)
    print("\n" + "=" * 70)
    print("  [Entry] 전략 조건 ALL 충족 — 신규 진입 후보")
    print("=" * 70)
    if len(entry_list) == 0:
        print("  현재 조건을 충족하는 신규 진입 후보가 없습니다.")
    else:
        for rank_i, (_, row) in enumerate(entry_list.iterrows(), 1):
            status = "보유중" if row['holding'] else "[*] 신규진입"
            print(f"  {rank_i:>2}. {row['name']:<16} | 현재가: {row['close']:>8,.0f}원 | "
                  f"6M수익률: {row['mom_6m']:>+6.1%} | ADX: {row['adx']:.1f} | {status}")


# ==================================================================
# 7. 시각화
# ==================================================================
def plot_results(cum_strat, drawdown, kospi_close, bt_dates, trade_log):
    """전략 vs 코스피 누적 수익률 + MDD 차트."""
    
    # 코스피 정규화
    kospi_bt = kospi_close.reindex(bt_dates).ffill()
    kospi_cum = kospi_bt / kospi_bt.iloc[0]
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 12),
                             gridspec_kw={'height_ratios': [3, 1.5, 1],
                                          'hspace': 0.04})
    
    ax1, ax2, ax3 = axes
    
    # --- 누적 수익률 ---
    ax1.plot(cum_strat.index, cum_strat.values * 100 - 100,
             color='#2196F3', linewidth=2, label='전략 수익률')
    ax1.plot(kospi_cum.index, (kospi_cum.values - 1) * 100,
             color='#FF5722', linewidth=1.5, linestyle='--', label='코스피 Buy&Hold')
    ax1.axhline(0, color='gray', linewidth=0.7, linestyle=':')
    ax1.set_ylabel('누적 수익률 (%)', fontsize=11)
    ax1.set_title('KOSPI 200 상대 모멘텀 + 추세 추종 전략 vs 코스피 지수', fontsize=14, pad=12)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.tick_params(labelbottom=False)
    
    # 최종 수익률 주석
    final_strat  = cum_strat.iloc[-1] * 100 - 100
    final_kospi  = (kospi_cum.iloc[-1] - 1) * 100
    ax1.annotate(f'전략: {final_strat:+.1f}%',
                 xy=(cum_strat.index[-1], final_strat),
                 xytext=(-80, 10), textcoords='offset points',
                 fontsize=9, color='#2196F3',
                 arrowprops=dict(arrowstyle='->', color='#2196F3'))
    ax1.annotate(f'코스피: {final_kospi:+.1f}%',
                 xy=(kospi_cum.index[-1], final_kospi),
                 xytext=(-80, -20), textcoords='offset points',
                 fontsize=9, color='#FF5722',
                 arrowprops=dict(arrowstyle='->', color='#FF5722'))
    
    # 거래 시점 표시
    if trade_log:
        tl = pd.DataFrame(trade_log)
        for _, row in tl.iterrows():
            if row['entry_date'] in cum_strat.index:
                ax1.axvline(row['entry_date'], color='green', alpha=0.15, linewidth=0.7)
    
    # --- MDD ---
    ax2.fill_between(drawdown.index, drawdown.values * 100, 0,
                     color='#F44336', alpha=0.4, label='MDD')
    ax2.plot(drawdown.index, drawdown.values * 100, color='#F44336', linewidth=1)
    ax2.set_ylabel('Drawdown (%)', fontsize=10)
    ax2.legend(loc='lower left', fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.tick_params(labelbottom=False)
    
    # --- 월별 보유 종목 수 (포지션 활용도) ---
    # 일별 포지션 수 근사: 거래 기록으로 계산
    if trade_log:
        pos_count = pd.Series(0, index=bt_dates)
        for _, row in pd.DataFrame(trade_log).iterrows():
            mask = (pos_count.index >= row['entry_date']) & (pos_count.index < row['exit_date'])
            pos_count[mask] += 1
        ax3.fill_between(pos_count.index, pos_count.values,
                         color='#9C27B0', alpha=0.5, label='보유 종목 수')
        ax3.axhline(TOP_K, color='purple', linestyle='--', linewidth=0.8, alpha=0.6)
        ax3.set_ylabel('보유 종목', fontsize=10)
        ax3.set_ylim(0, TOP_K + 2)
        ax3.legend(loc='upper right', fontsize=9)
    else:
        ax3.text(0.5, 0.5, '거래 없음', transform=ax3.transAxes, ha='center')
    
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=30, ha='right')
    
    plt.tight_layout()
    
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "kospi200_momentum_result.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"\n  [Chart] 차트 저장: {save_path}")
    plt.show()
    
    return save_path


# ==================================================================
# 8. 한계점 명시
# ==================================================================
def print_limitations():
    print("\n" + "=" * 60)
    print("  [!]  분석 한계점 및 주의사항")
    print("=" * 60)
    print("""
  1. [생존 편향] 유니버스를 '현재' KOSPI 200 구성 종목 기준으로
     구성했습니다. 백테스트 기간 중 상장 폐지·편출된 종목은 
     포함되지 않아 실제 성과보다 과대평가될 수 있습니다.

  2. [거래 비용] 왕복 0.2% (수수료 0.015% × 2 + 증권거래세
     0.18%)를 반영했으나, 시장 충격(Market Impact)과 슬리피지
     (가격 미끄러짐)는 미반영 상태입니다.

  3. [유동성 리스크] 소형주 진입 시 실제 체결가가 시가보다 
     불리할 수 있으나, 시가 체결로 가정합니다.

  4. [Look-ahead Bias] 신호는 t 종가, 체결은 t+1 시가로 
     엄격히 분리하여 편향을 최소화했습니다.

  5. [ADX 계산] Welles Wilder 평활법(alpha=1/14)을 적용하여
     표준 ADX와 동일한 방식을 사용합니다.

  6. [분할 매수/부분 청산] 미지원. 포지션당 10% 고정 비중 가정.

  7. [세금 처리] 양도소득세 등 투자자별 세금 효과는 미반영.

  * 본 결과는 과거 데이터 기반 참고용이며, 미래 수익을 
    보장하지 않습니다.
""")


# ==================================================================
# 9. 메인 실행
# ==================================================================
def main():
    print("=" * 60)
    print("  KOSPI 200 상대 모멘텀 + 추세 추종 백테스트")
    print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 데이터 다운로드
    (stock_close, stock_open, stock_high, stock_low,
     kospi_close, kospi_open, valid_tickers) = download_data(
        KOSPI_TOP50_TICKERS, START_DATE, END_DATE
    )
    
    # 2. 지표 계산
    print("\n[지표 계산 중...]")
    ma20, ma60, high20, adx_5ma = compute_indicators(
        stock_close, stock_open, stock_high, stock_low
    )
    
    # 3. 백테스트 실행
    daily_rets, bt_dates, trade_log, positions = run_backtest(
        valid_tickers, stock_close, stock_open,
        stock_high, stock_low, kospi_close, kospi_open
    )
    
    # 4. 성과 지표 출력
    cum_strat, drawdown, rets = calc_performance(
        daily_rets, bt_dates, trade_log, positions, stock_close
    )
    
    # 5. 현재 신호 스캔
    scan_current_signals(
        valid_tickers, stock_close, stock_open,
        stock_high, stock_low, ma20, ma60, high20, adx_5ma, positions
    )
    
    # 6. 거래 내역 상위 출력
    if trade_log:
        tl = pd.DataFrame(trade_log).sort_values('return', ascending=False)
        print("\n  [Log] 완료된 거래 내역 (수익률 상위 10)")
        print("-" * 65)
        print(f"  {'종목':<14} {'매수일':>12} {'매도일':>12} {'수익률':>8} {'청산사유':>8}")
        print("-" * 65)
        for _, r in tl.head(10).iterrows():
            print(f"  {r['name']:<14} {str(r['entry_date'].date()):>12} "
                  f"{str(r['exit_date'].date()):>12} {r['return']:>+7.2%} {r['exit_reason']:>8}")
        print("-" * 65)
        print(f"\n  [손절 거래]")
        stops = tl[tl['exit_reason'] == '손절']
        if len(stops) > 0:
            for _, r in stops.iterrows():
                print(f"    {r['name']:<14} {str(r['entry_date'].date()):>12} "
                      f"{str(r['exit_date'].date()):>12} {r['return']:>+7.2%}")
        else:
            print("    없음")
    
    # 7. 시각화
    plot_results(cum_strat, drawdown, kospi_close, bt_dates, trade_log)
    
    # 8. 한계점
    print_limitations()

if __name__ == "__main__":
    main()
