"""
개선된 이동평균 교차 전략 백테스트
──────────────────────────────────
진입 : ① 종가 > 최근 20일 최고가  ② MA20 > MA60  ③ ADX(14) 5일 평균 ≥ 25
청산 : ① MA20이 MA60 하향 돌파     ② 매수가 대비 -5% 손절
재진입: 손절 후 새로운 골든크로스 발생 전까지 진입 금지
비용  : 매매당 0.1% 수수료
비교  : 기존 전략(MA20/60 교차) vs 개선 전략 vs Buy & Hold

[피라미딩 추가 전략] (개선 전략의 진입/청산 조건 유지 + 분할매수)
1차  : 개선 전략 진입 신호 → 자본의 FIRST_ENTRY_RATIO 매수
2차  : 1차 매수가 대비 +5% → 잔여 현금의 25% 추가 매수
3차  : 2차 매수가 대비 +5% → 잔여 현금의 25% 추가 매수
4차  : 52주 신고가 갱신     → 잔여 현금의 20% 추가 매수
간격 : 각 단계 사이 최소 5거래일
청산 : 데드크로스 또는 보유 중 고점 대비 -10% 트레일링 스탑 (고정 손절 대체)
"""

import os, warnings, platform
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import yfinance as yf
from matplotlib import rcParams

warnings.filterwarnings("ignore")

# ── 한글 폰트 설정 ─────────────────────────────────────────────────
if platform.system() == "Windows":
    rcParams["font.family"] = "Malgun Gothic"
elif platform.system() == "Darwin":
    rcParams["font.family"] = "AppleGothic"
else:
    rcParams["font.family"] = "NanumGothic"
rcParams["axes.unicode_minus"] = False

# ── 경로 설정 ──────────────────────────────────────────────────────
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

import os
os.makedirs(SAVE_DIR, exist_ok=True)

# ── 파라미터 ───────────────────────────────────────────────────────
TICKERS     = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
START_DATE  = "2023-03-27"   # 백테스트 시작일 (포함)
END_DATE    = "2026-03-23"   # 백테스트 종료일 (포함)
WARMUP_DAYS = 450            # 지표(MA60·ADX·52주 신고가) 사전 계산용 추가 다운로드 기간(달력일)
PERIOD_TAG  = f"{START_DATE.replace('-', '')}_{END_DATE.replace('-', '')}"   # 결과 파일명 구분용
COMMISSION = 0.001     # 수수료 0.1%
STOPLOSS   = -0.05     # 손절 -5%
ADX_PERIOD = 14
ADX_MA     = 5         # ADX 평활 기간
ADX_THRESH = 25        # ADX 필터 기준값

# ── 피라미딩 파라미터 ──────────────────────────────────────────────
FIRST_ENTRY_RATIO = 0.50   # 1차 매수 비중 (100%면 잔여 현금이 없어 추가매수 불가)
PYRAMID_STEP      = 0.05   # 2·3차: 직전 매수가 대비 +5%
PYRAMID_RATIOS    = {2: 0.25, 3: 0.25, 4: 0.20}   # 단계별 잔여 현금 투입 비율
PYRAMID_GAP       = 5      # 단계 사이 최소 거래일
HIGH_52W          = 252    # 52주 ≈ 252거래일
TRAIL_STOP        = -0.10  # 고점 대비 -10% 트레일링 스탑


# ══════════════════════════════════════════════════════════════════
#  보조 함수
# ══════════════════════════════════════════════════════════════════

def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """True Range 기반 ADX 계산 (Close 기준 단순화 버전)."""
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]

    # +DM / -DM
    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm   = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm  = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder 평활
    def wilder_smooth(series, n):
        result = series.copy() * np.nan
        result.iloc[n - 1] = series.iloc[:n].sum()
        for i in range(n, len(series)):
            result.iloc[i] = result.iloc[i - 1] - result.iloc[i - 1] / n + series.iloc[i]
        return result

    atr      = wilder_smooth(tr,                          period)
    plus_di  = 100 * wilder_smooth(pd.Series(plus_dm,  index=df.index), period) / atr
    minus_di = 100 * wilder_smooth(pd.Series(minus_dm, index=df.index), period) / atr

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], 0)
    adx = wilder_smooth(dx.fillna(0), period)
    return adx


def calc_mdd(cum: pd.Series) -> float:
    """최대 낙폭(MDD) 계산."""
    return ((cum - cum.cummax()) / cum.cummax()).min()


# ══════════════════════════════════════════════════════════════════
#  데이터 다운로드 & 지표 계산
# ══════════════════════════════════════════════════════════════════
print("데이터 다운로드 중...")
raw = yf.download(
    tickers   = list(TICKERS.values()),
    start     = (pd.Timestamp(START_DATE) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d"),
    end       = (pd.Timestamp(END_DATE) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    interval  = "1d",
    auto_adjust = True,
    progress  = True,
)

dfs = {}
for name, ticker in TICKERS.items():
    df = raw.xs(ticker, axis=1, level=1).copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    df.columns.name = None
    df.dropna(subset=["Close"], inplace=True)

    df["MA_20"]      = df["Close"].rolling(20).mean()
    df["MA_60"]      = df["Close"].rolling(60).mean()
    df["High_20"]    = df["High"].rolling(20).max()        # 최근 20일 최고가
    df["ADX"]        = calc_adx(df, ADX_PERIOD)
    df["ADX_MA5"]    = df["ADX"].rolling(ADX_MA).mean()    # 5일 평균 ADX
    df["Open_next"]  = df["Open"].shift(-1)                 # 익일 시가
    df["High_52W"]   = (df["High"].rolling(HIGH_52W, min_periods=HIGH_52W)
                        .max().shift(1))                     # 전일까지 52주 최고가
    df = df.loc[START_DATE:END_DATE]                         # 지표 계산 후 백테스트 기간만 사용
    dfs[name] = df
    print(f"  {name}: {len(df)}행 로드 완료")


# ══════════════════════════════════════════════════════════════════
#  기존 전략 (MA20/60 교차)
# ══════════════════════════════════════════════════════════════════

def run_old_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """기존 전략: MA20 > MA60 → 익일 진입/청산."""
    bt = df[["Close", "MA_20", "MA_60"]].dropna().copy()
    bt["raw_signal"] = (bt["MA_20"] > bt["MA_60"]).astype(int)
    bt["position"]   = bt["raw_signal"].shift(1).fillna(0)
    bt["trade"]      = bt["position"].diff().abs().fillna(0)
    bt["cost"]       = bt["trade"] * COMMISSION
    bt["ret"]        = bt["Close"].pct_change().fillna(0)
    bt["strat_ret"]  = bt["position"] * bt["ret"] - bt["cost"]
    bt["cum_strat"]  = (1 + bt["strat_ret"]).cumprod()
    bt["cum_bnh"]    = (1 + bt["ret"]).cumprod()
    return bt


# ══════════════════════════════════════════════════════════════════
#  개선 전략 (이벤트 기반 루프)
# ══════════════════════════════════════════════════════════════════

def run_improved_strategy(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    개선 전략:
    진입 : ① Close > High_20(전일)  ② MA20 > MA60  ③ ADX_MA5 ≥ 25
    청산 : ① MA20 < MA60 (데드크로스)  ② 매수가 대비 -5% 손절
    재진입: 손절 후 새로운 골든크로스 전까지 금지
    """
    cols = ["Close", "Open", "High", "Low",
            "MA_20", "MA_60", "High_20", "ADX_MA5", "Open_next"]
    bt = df[cols].dropna().copy()

    n = len(bt)
    closes     = bt["Close"].values
    opens_next = bt["Open_next"].values     # 익일 시가 (실행가)
    ma20       = bt["MA_20"].values
    ma60       = bt["MA_60"].values
    high20     = bt["High_20"].values
    adx5       = bt["ADX_MA5"].values

    position       = np.zeros(n)
    daily_strategy = np.zeros(n)

    in_position        = False
    buy_price          = np.nan
    blocked_after_sl   = False   # 손절 후 재진입 금지 플래그
    golden_cross_seen  = False   # 손절 이후 새 골든크로스 여부

    was_golden = (ma20[0] > ma60[0])   # 이전 봉 상태 초기화

    trades = []   # 개별 거래 기록

    for i in range(1, n - 1):          # i = 오늘 (신호 확인), i+1 = 내일 (실행)
        # ── 골든크로스 감지 (손절 후 해제 조건) ──────────────────
        new_golden = (ma20[i] > ma60[i])
        if not was_golden and new_golden:
            golden_cross_seen = True   # 새 골든크로스 발생
        was_golden = new_golden

        # ── 포지션 보유 중 ────────────────────────────────────────
        if in_position:
            position[i] = 1

            # 청산 조건 1: 데드크로스
            dead_cross = (ma20[i] < ma60[i])
            # 청산 조건 2: 손절 (다음 거래일 시가 기준 예비 확인은 당일 종가로)
            sl_hit = (closes[i] / buy_price - 1) <= STOPLOSS

            if dead_cross or sl_hit:
                # 익일 시가에 청산
                exit_price = opens_next[i]
                trade_ret  = exit_price / buy_price - 1 - COMMISSION
                trades.append({
                    "exit_idx"  : i + 1,
                    "trade_ret" : trade_ret,
                    "exit_type" : "손절" if sl_hit else "데드크로스",
                })
                # 청산 당일(i+1) 수익 반영은 ret 계산 시 처리
                if sl_hit:
                    blocked_after_sl  = True
                    golden_cross_seen = False   # 리셋
                in_position = False
                buy_price   = np.nan
                position[i + 1] = 0
                continue

        # ── 포지션 미보유 ─────────────────────────────────────────
        else:
            position[i] = 0

            # 재진입 금지 해제 확인
            if blocked_after_sl:
                if golden_cross_seen:
                    blocked_after_sl = False
                else:
                    continue   # 아직 금지 상태

            # 진입 조건 확인 (전일 High_20 : i-1 기준)
            cond1 = closes[i] > high20[i - 1]          # 20일 최고가 돌파
            cond2 = new_golden                           # MA20 > MA60
            cond3 = adx5[i] >= ADX_THRESH               # ADX 필터

            if cond1 and cond2 and cond3:
                buy_price  = opens_next[i]              # 익일 시가 매수
                in_position = True
                position[i + 1] = 1
                trades.append({
                    "entry_idx" : i + 1,
                    "buy_price" : buy_price,
                    "exit_idx"  : None,
                    "trade_ret" : None,
                    "exit_type" : None,
                })

    # ── 수익률 계산 ───────────────────────────────────────────────
    bt["position"] = position
    bt["trade"]    = pd.Series(position, index=bt.index).diff().abs().fillna(0)
    bt["cost"]     = bt["trade"] * COMMISSION
    bt["ret"]      = bt["Close"].pct_change().fillna(0)
    bt["strat_ret"] = bt["position"] * bt["ret"] - bt["cost"]
    bt["cum_strat"] = (1 + bt["strat_ret"]).cumprod()
    bt["cum_bnh"]   = (1 + bt["ret"]).cumprod()

    return bt, trades


# ══════════════════════════════════════════════════════════════════
#  성과 분석
# ══════════════════════════════════════════════════════════════════

def analyze_trades(trades: list) -> dict:
    """개별 거래 목록에서 승률, 평균 수익/손실 분석."""
    closed = [t for t in trades if t.get("trade_ret") is not None]
    if not closed:
        return {"win_rate": 0, "avg_win": 0, "avg_loss": 0,
                "profit_factor": 0, "n_trades": 0}

    rets  = [t["trade_ret"] for t in closed]
    wins  = [r for r in rets if r > 0]
    losses= [r for r in rets if r <= 0]

    win_rate      = len(wins) / len(rets) if rets else 0
    avg_win       = np.mean(wins)   if wins   else 0
    avg_loss      = np.mean(losses) if losses else 0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else np.inf

    return {
        "n_trades"     : len(rets),
        "win_rate"     : win_rate,
        "avg_win"      : avg_win,
        "avg_loss"     : avg_loss,
        "profit_factor": profit_factor,
    }


def print_summary(name: str, old_bt: pd.DataFrame,
                  new_bt: pd.DataFrame, trades: list):
    """콘솔에 성과 요약 출력."""
    stats = analyze_trades(trades)

    old_total = old_bt["cum_strat"].iloc[-1] - 1
    new_total = new_bt["cum_strat"].iloc[-1] - 1
    bnh_total = new_bt["cum_bnh"].iloc[-1]   - 1

    old_mdd = calc_mdd(old_bt["cum_strat"])
    new_mdd = calc_mdd(new_bt["cum_strat"])
    bnh_mdd = calc_mdd(new_bt["cum_bnh"])

    # 기존 전략 매매 횟수
    old_trades = int(old_bt["trade"].sum())

    print(f"\n{'═'*60}")
    print(f"  [{name}] 전략 성과 비교")
    print(f"{'═'*60}")
    print(f"  {'항목':<18} {'기존 전략':>10} {'개선 전략':>10} {'B&H':>10}")
    print(f"  {'─'*52}")
    print(f"  {'총 수익률':<18} {old_total*100:>+9.2f}% {new_total*100:>+9.2f}% {bnh_total*100:>+9.2f}%")
    print(f"  {'MDD':<18} {old_mdd*100:>9.2f}% {new_mdd*100:>9.2f}% {bnh_mdd*100:>9.2f}%")
    print(f"  {'매매 횟수':<18} {old_trades:>10} {stats['n_trades']:>10} {'─':>10}")
    print(f"  {'승률':<18} {'─':>10} {stats['win_rate']*100:>9.1f}% {'─':>10}")
    print(f"  {'평균 수익':<18} {'─':>10} {stats['avg_win']*100:>+9.2f}% {'─':>10}")
    print(f"  {'평균 손실':<18} {'─':>10} {stats['avg_loss']*100:>+9.2f}% {'─':>10}")
    print(f"  {'손익비(PF)':<18} {'─':>10} {stats['profit_factor']:>10.2f} {'─':>10}")
    print(f"{'═'*60}")

    # 노이즈 제거 효과 해석
    trade_reduction = (1 - stats["n_trades"] / max(old_trades, 1)) * 100
    print(f"\n  ■ 노이즈 제거 효과 분석")
    print(f"    · 매매 횟수 감소 : {old_trades} → {stats['n_trades']}회 "
          f"({trade_reduction:+.1f}%)")
    print(f"    · MDD 변화      : {old_mdd*100:.1f}% → {new_mdd*100:.1f}%")
    if stats["profit_factor"] > 1:
        print(f"    · 손익비 {stats['profit_factor']:.2f} : "
              f"평균 수익이 평균 손실의 {stats['profit_factor']:.2f}배 → 수익 구조 우위")
    if stats["avg_loss"] != 0:
        rr = abs(stats["avg_win"] / stats["avg_loss"])
        print(f"    · 수익/손실 비율 : {rr:.2f} "
              f"({'유리' if rr >= 1 else '불리'}한 비대칭 구조)")


# ══════════════════════════════════════════════════════════════════
#  백테스트 실행
# ══════════════════════════════════════════════════════════════════
all_results = {}

for name, df in dfs.items():
    print(f"\n── {name} 백테스트 실행 중...")
    old_bt           = run_old_strategy(df)
    new_bt, trades   = run_improved_strategy(df)
    print_summary(name, old_bt, new_bt, trades)

    stats = analyze_trades(trades)
    all_results[name] = {
        "old_bt": old_bt,
        "new_bt": new_bt,
        "trades": trades,
        "stats" : stats,
    }


# ══════════════════════════════════════════════════════════════════
#  누적 수익률 비교 차트 (2×1)
# ══════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 1, figsize=(15, 11), sharex=False)
fig.suptitle(
    "MA 전략 개선 효과 비교\n기존 전략 vs 개선 전략 vs Buy & Hold",
    fontsize=15, fontweight="bold", y=1.00,
)

COLORS = {
    "old"     : "#ff7f0e",   # 주황
    "improved": "#e84545",   # 빨강
    "bnh"     : "#2196f3",   # 파랑
}

for ax, (name, res) in zip(axes, all_results.items()):
    old_bt = res["old_bt"]
    new_bt = res["new_bt"]
    stats  = res["stats"]

    old_total = old_bt["cum_strat"].iloc[-1] - 1
    new_total = new_bt["cum_strat"].iloc[-1] - 1
    bnh_total = new_bt["cum_bnh"].iloc[-1]   - 1

    old_mdd = calc_mdd(old_bt["cum_strat"])
    new_mdd = calc_mdd(new_bt["cum_strat"])

    ax.plot(old_bt.index, (old_bt["cum_strat"] - 1) * 100,
            color=COLORS["old"],      lw=1.5, alpha=0.85,
            label=f"기존 전략  ({old_total*100:+.1f}%, MDD {old_mdd*100:.1f}%)")
    ax.plot(new_bt.index, (new_bt["cum_strat"] - 1) * 100,
            color=COLORS["improved"], lw=1.8,
            label=f"개선 전략  ({new_total*100:+.1f}%, MDD {new_mdd*100:.1f}%)")
    ax.plot(new_bt.index, (new_bt["cum_bnh"] - 1) * 100,
            color=COLORS["bnh"],      lw=1.5, ls="--", alpha=0.85,
            label=f"Buy & Hold ({bnh_total*100:+.1f}%)")

    ax.axhline(0, color="gray", lw=0.7, ls=":")
    ax.fill_between(new_bt.index,
                    (new_bt["cum_strat"] - 1) * 100,
                    alpha=0.07, color=COLORS["improved"])

    # 정보 박스
    pf  = stats.get("profit_factor", 0)
    wr  = stats.get("win_rate", 0) * 100
    nt  = stats.get("n_trades", 0)
    aw  = stats.get("avg_win",  0) * 100
    al  = stats.get("avg_loss", 0) * 100
    rr  = abs(aw / al) if al != 0 else 0

    textstr = (
        f"[개선 전략 성과]\n"
        f"승률  : {wr:.1f}%   매매 : {nt}회\n"
        f"평균 수익 : {aw:+.2f}%\n"
        f"평균 손실 : {al:+.2f}%\n"
        f"수익/손실 비 : {rr:.2f}   PF : {pf:.2f}"
    )
    ax.text(0.01, 0.97, textstr,
            transform=ax.transAxes, fontsize=8.5,
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.45",
                      fc="white", alpha=0.82, ec="silver"))

    ax.set_title(name, fontsize=13, fontweight="bold", pad=8)
    ax.set_ylabel("누적 수익률 (%)", fontsize=10)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:+.0f}%"))
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.85)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

axes[-1].set_xlabel("날짜", fontsize=10)
plt.tight_layout()

out_path = os.path.join(SAVE_DIR, f"improved_backtest_{PERIOD_TAG}.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"\n차트 저장 완료 → {out_path}")


# ══════════════════════════════════════════════════════════════════
#  피라미딩 전략 (자본/현금 기반 이벤트 루프)
# ══════════════════════════════════════════════════════════════════

def run_position_strategy(df: pd.DataFrame, pyramid: bool) -> tuple[pd.DataFrame, list, list]:
    """
    개선 전략의 진입/청산 조건을 현금·보유수량 기준으로 체결하는 엔진.
    신호는 당일 종가로 판단하고 익일 시가에 체결한다.

    pyramid=False : 기존(개선) 전략 — 자본 100% 진입, 매수가 대비 -5% 고정 손절
    pyramid=True  : 피라미딩 전략 — 1~4차 분할매수, 고점 대비 -10% 트레일링 스탑
    """
    cols = ["Close", "Open", "High", "Low",
            "MA_20", "MA_60", "High_20", "ADX_MA5", "Open_next"]
    bt = df[cols].dropna().copy()
    # 전일까지의 52주 최고가 (데이터 1년 미만 구간은 NaN → 4차 매수 불가)
    high52 = df["High_52W"].reindex(bt.index).values

    n      = len(bt)
    closes = bt["Close"].values
    opens  = bt["Open"].values
    ma20   = bt["MA_20"].values
    ma60   = bt["MA_60"].values
    high20 = bt["High_20"].values
    adx5   = bt["ADX_MA5"].values

    cash, shares = 1.0, 0.0
    equity = np.zeros(n)
    pending = None            # 익일 시가에 체결할 주문: ("buy", 단계, 비율) / ("sell", 사유)

    in_position    = False
    stage          = 0        # 현재 체결된 최종 단계 (0 = 미보유)
    entry_price    = np.nan   # 1차 매수가 (고정 손절 기준)
    last_buy_price = np.nan
    last_buy_idx   = -PYRAMID_GAP
    peak           = np.nan   # 보유 중 최고 종가 (트레일링 스탑 기준)
    trade          = None

    blocked_after_sl  = False
    golden_cross_seen = False
    was_golden        = (ma20[0] > ma60[0])

    trades     = []           # 청산 완료 거래
    buy_events = []           # (날짜, 단계)

    for i in range(n):
        # ── 1) 전일 신호 → 당일 시가 체결 ─────────────────────────
        if pending is not None:
            px = opens[i]
            if pending[0] == "buy":
                _, stage_no, ratio = pending
                amount  = cash * ratio
                shares += amount * (1 - COMMISSION) / px
                cash   -= amount
                trade["cost"] += amount
                stage, last_buy_price, last_buy_idx = stage_no, px, i
                if stage_no == 1:
                    entry_price = px
                    peak        = px
                buy_events.append((bt.index[i], stage_no))
            else:
                proceeds = shares * px * (1 - COMMISSION)
                cash    += proceeds
                pnl      = proceeds - trade["cost"]
                trade.update(exit_idx=i, pnl=pnl,
                             trade_ret=pnl / trade["cost"], exit_type=pending[1])
                trades.append(trade)
                trade, shares, stage = None, 0.0, 0
            pending = None

        equity[i] = cash + shares * closes[i]

        # 신호 판단은 기존 루프와 동일하게 1 ~ n-2 구간
        if i == 0 or i >= n - 1:
            continue

        new_golden = (ma20[i] > ma60[i])
        if not was_golden and new_golden:
            golden_cross_seen = True
        was_golden = new_golden

        # ── 2) 보유 중: 청산 → 피라미딩 순으로 확인 ────────────────
        if in_position:
            peak       = max(peak, closes[i])
            dead_cross = (ma20[i] < ma60[i])
            if pyramid:
                sl_hit, sl_name = closes[i] <= peak * (1 + TRAIL_STOP), "트레일링스탑"
            else:
                sl_hit, sl_name = (closes[i] / entry_price - 1) <= STOPLOSS, "손절"

            if dead_cross or sl_hit:
                pending = ("sell", sl_name if sl_hit else "데드크로스")
                if sl_hit:
                    blocked_after_sl  = True
                    golden_cross_seen = False
                in_position = False
                continue

            if pyramid and 1 <= stage < 4 and (i + 1 - last_buy_idx) >= PYRAMID_GAP:
                if stage in (1, 2):
                    add = closes[i] >= last_buy_price * (1 + PYRAMID_STEP)
                else:
                    add = not np.isnan(high52[i]) and closes[i] > high52[i]
                if add:
                    pending = ("buy", stage + 1, PYRAMID_RATIOS[stage + 1])

        # ── 3) 미보유: 개선 전략과 동일한 진입 조건 ────────────────
        else:
            if blocked_after_sl:
                if golden_cross_seen:
                    blocked_after_sl = False
                else:
                    continue

            cond1 = closes[i] > high20[i - 1]
            cond2 = new_golden
            cond3 = adx5[i] >= ADX_THRESH
            if cond1 and cond2 and cond3:
                pending     = ("buy", 1, FIRST_ENTRY_RATIO if pyramid else 1.0)
                in_position = True
                trade       = {"entry_idx": i + 1, "cost": 0.0}

    # 기간 말 미청산 포지션은 마지막 종가로 평가해 거래에 포함
    if trade is not None and shares > 0:
        pnl = shares * closes[-1] * (1 - COMMISSION) - trade["cost"]
        trade.update(exit_idx=n - 1, pnl=pnl,
                     trade_ret=pnl / trade["cost"], exit_type="기간말 평가")
        trades.append(trade)

    bt["equity"]  = equity
    bt["cum_bnh"] = bt["Close"] / bt["Close"].iloc[0]
    return bt, trades, buy_events


def calc_metrics(equity: pd.Series, trades: list | None) -> dict:
    """총 수익률, CAGR, MDD, 샤프(무위험수익률 0, 연 252일), 승률, Profit Factor."""
    eq    = equity / equity.iloc[0]
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    rets  = eq.pct_change().dropna()
    m = {
        "total" : eq.iloc[-1] - 1,
        "cagr"  : eq.iloc[-1] ** (1 / years) - 1,
        "mdd"   : calc_mdd(eq),
        "sharpe": rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0.0,
    }
    if trades is None:        # Buy & Hold
        m.update(win_rate=np.nan, pf=np.nan, n_trades=np.nan)
        return m
    pnls   = [t["pnl"] for t in trades]
    wins   = sum(p for p in pnls if p > 0)
    losses = sum(p for p in pnls if p <= 0)
    m["n_trades"] = len(pnls)
    m["win_rate"] = sum(p > 0 for p in pnls) / len(pnls) if pnls else 0.0
    m["pf"]       = wins / abs(losses) if losses < 0 else np.inf
    return m


def print_pyramid_comparison(name: str, base: dict, pyr: dict, bnh: dict,
                             buy_events: list):
    rows = [
        ("총 수익률",     "total",    lambda v: f"{v*100:+.2f}%"),
        ("CAGR",          "cagr",     lambda v: f"{v*100:+.2f}%"),
        ("MDD",           "mdd",      lambda v: f"{v*100:.2f}%"),
        ("샤프 비율",     "sharpe",   lambda v: f"{v:.2f}"),
        ("승률",          "win_rate", lambda v: f"{v*100:.1f}%"),
        ("Profit Factor", "pf",       lambda v: f"{v:.2f}"),
        ("거래 횟수",     "n_trades", lambda v: f"{v:.0f}"),
    ]
    fmt = lambda f, v: "─" if (isinstance(v, float) and np.isnan(v)) else f(v)

    print(f"\n{'═'*62}")
    print(f"  [{name}] 기존 전략 vs 피라미딩 추가 전략")
    print(f"{'═'*62}")
    print(f"  {'항목':<14} {'기존 전략':>12} {'피라미딩':>12} {'B&H':>12}")
    print(f"  {'─'*56}")
    for label, key, f in rows:
        print(f"  {label:<14} {fmt(f, base[key]):>12} "
              f"{fmt(f, pyr[key]):>12} {fmt(f, bnh[key]):>12}")
    print(f"{'═'*62}")
    counts = {s: sum(1 for _, st in buy_events if st == s) for s in range(1, 5)}
    print("  피라미딩 체결 횟수 : " +
          "  ".join(f"{s}차 {c}회" for s, c in counts.items()))


pyramid_results = {}
for name, df in dfs.items():
    print(f"\n── {name} 피라미딩 백테스트 실행 중...")
    base_bt, base_trades, _       = run_position_strategy(df, pyramid=False)
    pyr_bt,  pyr_trades,  events  = run_position_strategy(df, pyramid=True)
    base_m = calc_metrics(base_bt["equity"], base_trades)
    pyr_m  = calc_metrics(pyr_bt["equity"],  pyr_trades)
    bnh_m  = calc_metrics(pyr_bt["cum_bnh"], None)
    print_pyramid_comparison(name, base_m, pyr_m, bnh_m, events)
    pyramid_results[name] = dict(base_bt=base_bt, pyr_bt=pyr_bt, events=events,
                                 base_m=base_m, pyr_m=pyr_m, bnh_m=bnh_m)


# ══════════════════════════════════════════════════════════════════
#  피라미딩 비교 차트 (2×1)
# ══════════════════════════════════════════════════════════════════
PYR_COLORS = {
    "base"   : "#8a8a8a",   # 기존 전략 (회색)
    "pyramid": "#e84545",   # 피라미딩 전략 (빨강)
    "bnh"    : "#2196f3",   # Buy & Hold (파랑 점선)
}
STAGE_COLORS = {1: "#2e7d32", 2: "#f9a825", 3: "#8e24aa", 4: "#111111"}

fig, axes = plt.subplots(2, 1, figsize=(15, 11))
fig.suptitle("피라미딩(분할매수) 효과 비교\n기존 전략 vs 피라미딩 전략 vs Buy & Hold",
             fontsize=15, fontweight="bold", y=1.00)

for ax, (name, res) in zip(axes, pyramid_results.items()):
    base_bt, pyr_bt = res["base_bt"], res["pyr_bt"]
    base_m, pyr_m, bnh_m = res["base_m"], res["pyr_m"], res["bnh_m"]
    pyr_cum = (pyr_bt["equity"] - 1) * 100

    ax.plot(base_bt.index, (base_bt["equity"] - 1) * 100,
            color=PYR_COLORS["base"], lw=1.5,
            label=f"기존 전략  ({base_m['total']*100:+.1f}%, MDD {base_m['mdd']*100:.1f}%)")
    ax.plot(pyr_bt.index, pyr_cum,
            color=PYR_COLORS["pyramid"], lw=1.8,
            label=f"피라미딩 전략 ({pyr_m['total']*100:+.1f}%, MDD {pyr_m['mdd']*100:.1f}%)")
    ax.plot(pyr_bt.index, (pyr_bt["cum_bnh"] - 1) * 100,
            color=PYR_COLORS["bnh"], lw=1.5, ls="--",
            label=f"Buy & Hold ({bnh_m['total']*100:+.1f}%)")

    # 피라미딩 진입 시점 ▲ (1~4차 색상 구분, 체결일의 피라미딩 누적수익률 위치)
    for s, color in STAGE_COLORS.items():
        dates = [d for d, st in res["events"] if st == s]
        if dates:
            ax.scatter(dates, pyr_cum.loc[dates], marker="^", s=70, color=color,
                       edgecolors="white", linewidths=0.8, zorder=5,
                       label=f"{s}차 매수 ({len(dates)}회)")

    ax.axhline(0, color="gray", lw=0.7, ls=":")
    ax.set_title(name, fontsize=13, fontweight="bold", pad=8)
    ax.set_ylabel("누적 수익률 (%)", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:+.0f}%"))
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.85, ncol=2)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

axes[-1].set_xlabel("날짜", fontsize=10)
plt.tight_layout()

pyr_path = os.path.join(SAVE_DIR, f"pyramid_comparison_{PERIOD_TAG}.png")
plt.savefig(pyr_path, dpi=150, bbox_inches="tight")
print(f"\n차트 저장 완료 → {pyr_path}")
plt.show()
