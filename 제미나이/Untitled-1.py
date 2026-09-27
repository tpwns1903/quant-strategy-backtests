
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import rcParams
import warnings, platform

warnings.filterwarnings("ignore")

if platform.system() == "Windows":
    rcParams["font.family"] = "Malgun Gothic"
elif platform.system() == "Darwin":
    rcParams["font.family"] = "AppleGothic"
else:
    rcParams["font.family"] = "NanumGothic"
rcParams["axes.unicode_minus"] = False

TICKERS = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
START_DATE = "2015-03-01"
END_DATE   = "2025-03-22"

raw_data = yf.download(
    tickers=list(TICKERS.values()),
    start=START_DATE,
    end=END_DATE,
    interval="1d",
    auto_adjust=True,
    progress=True,
)

dfs = {}
for name, ticker in TICKERS.items():
    df = raw_data.xs(ticker, axis=1, level=1).copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    df.columns.name = None
    df.dropna(subset=["Close"], inplace=True)
    df["MA_20"]  = df["Close"].rolling(20).mean()
    df["MA_60"]  = df["Close"].rolling(60).mean()
    df["MA_120"] = df["Close"].rolling(120).mean()
    df["MA_200"] = df["Close"].rolling(200).mean()
    dfs[name] = df

fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
fig.suptitle("KOSPI / KOSDAQ 종가 추이 (최근 10년)", fontsize=16, fontweight="bold", y=0.98)

COLORS = {"Close":"#1f77b4","MA_20":"#ff7f0e","MA_60":"#2ca02c","MA_120":"#d62728","MA_200":"#9467bd"}

for ax, (name, df) in zip(axes, dfs.items()):
    ax.fill_between(df.index, df["Close"], alpha=0.12, color=COLORS["Close"])
    ax.plot(df.index, df["Close"],  color=COLORS["Close"],  lw=1.4, label="종가")
    ax.plot(df.index, df["MA_20"],  color=COLORS["MA_20"],  lw=1.0, ls="--", label="MA 20")
    ax.plot(df.index, df["MA_60"],  color=COLORS["MA_60"],  lw=1.0, ls="--", label="MA 60")
    ax.plot(df.index, df["MA_120"], color=COLORS["MA_120"], lw=1.0, ls="-.", label="MA 120")
    ax.plot(df.index, df["MA_200"], color=COLORS["MA_200"], lw=1.0, ls="-.", label="MA 200")
    ax.set_title(name, fontsize=13, fontweight="bold", pad=8)
    ax.set_ylabel("지수", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.legend(loc="upper left", fontsize=8, framealpha=0.7)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)

axes[-1].set_xlabel("날짜", fontsize=10)
plt.tight_layout()
plt.savefig("kospi_kosdaq_close.png", dpi=150, bbox_inches="tight")

for name, df in dfs.items():
    df.to_csv(f"{name.lower()}_10y.csv")

# ══════════════════════════════════════════════════════════════════
#  이동평균선 교차 전략 백테스트  (MA20 vs MA60)
# ══════════════════════════════════════════════════════════════════
COMMISSION = 0.001   # 왕복 수수료 0.1%

def run_backtest(df: pd.DataFrame, name: str) -> dict:
    """골든크로스/데드크로스 전략 백테스트를 수행하고 결과 딕셔너리를 반환."""
    bt = df[["Close", "MA_20", "MA_60"]].copy().dropna()

    # ── 1. 신호 생성 ──────────────────────────────────────────────
    # MA20 > MA60 이면 1(롱), 아니면 0(현금)
    bt["raw_signal"] = (bt["MA_20"] > bt["MA_60"]).astype(int)

    # 다음 거래일에 실행 → shift(1)
    bt["position"] = bt["raw_signal"].shift(1).fillna(0)

    # ── 2. 거래 감지 & 수수료 반영 ───────────────────────────────
    # 포지션 변화가 발생한 날 수수료 차감
    bt["trade"] = bt["position"].diff().abs().fillna(0)   # 0 또는 1
    bt["cost"]  = bt["trade"] * COMMISSION

    # ── 3. 일간 수익률 ───────────────────────────────────────────
    bt["daily_return"]    = bt["Close"].pct_change().fillna(0)
    bt["strategy_return"] = bt["position"] * bt["daily_return"] - bt["cost"]

    # ── 4. 누적 수익률 ───────────────────────────────────────────
    bt["cum_strategy"] = (1 + bt["strategy_return"]).cumprod()
    bt["cum_bnh"]      = (1 + bt["daily_return"]).cumprod()

    # ── 5. MDD 계산 ──────────────────────────────────────────────
    def calc_mdd(cum_series: pd.Series) -> float:
        peak    = cum_series.cummax()
        drawdown = (cum_series - peak) / peak
        return drawdown.min()   # 음수

    mdd_strategy = calc_mdd(bt["cum_strategy"])
    mdd_bnh      = calc_mdd(bt["cum_bnh"])

    total_ret_strategy = bt["cum_strategy"].iloc[-1] - 1
    total_ret_bnh      = bt["cum_bnh"].iloc[-1] - 1

    # ── 6. 매매 횟수 ─────────────────────────────────────────────
    n_trades = int(bt["trade"].sum())

    print(f"\n{'─'*50}")
    print(f"  [{name}] 백테스트 결과  ({bt.index[0].date()} ~ {bt.index[-1].date()})")
    print(f"{'─'*50}")
    print(f"  전략 총 수익률 : {total_ret_strategy*100:+.2f}%")
    print(f"  B&H  총 수익률 : {total_ret_bnh*100:+.2f}%")
    print(f"  전략 MDD       : {mdd_strategy*100:.2f}%")
    print(f"  B&H  MDD       : {mdd_bnh*100:.2f}%")
    print(f"  매매 횟수       : {n_trades}회")
    print(f"{'─'*50}")

    return {
        "name"         : name,
        "bt"           : bt,
        "total_strategy": total_ret_strategy,
        "total_bnh"    : total_ret_bnh,
        "mdd_strategy" : mdd_strategy,
        "mdd_bnh"      : mdd_bnh,
        "n_trades"     : n_trades,
    }

# ── 백테스트 실행 ─────────────────────────────────────────────────
results = {name: run_backtest(df, name) for name, df in dfs.items()}

# ── 누적 수익률 비교 차트 ─────────────────────────────────────────
fig2, axes2 = plt.subplots(2, 1, figsize=(14, 10), sharex=False)
fig2.suptitle(
    "MA 20/60 교차 전략 vs Buy & Hold\n누적 수익률 비교",
    fontsize=15, fontweight="bold", y=0.99,
)

PALETTE = {
    "strategy" : "#e84545",   # 빨강 계열
    "bnh"      : "#2196f3",   # 파랑 계열
}

for ax, (name, res) in zip(axes2, results.items()):
    bt = res["bt"]

    ax.plot(bt.index, (bt["cum_strategy"] - 1) * 100,
            color=PALETTE["strategy"], lw=1.6,
            label=f"MA 교차 전략  ({res['total_strategy']*100:+.1f}%)")
    ax.plot(bt.index, (bt["cum_bnh"] - 1) * 100,
            color=PALETTE["bnh"], lw=1.6, ls="--",
            label=f"Buy & Hold  ({res['total_bnh']*100:+.1f}%)")

    ax.axhline(0, color="gray", lw=0.8, ls=":")
    ax.fill_between(
        bt.index,
        (bt["cum_strategy"] - 1) * 100,
        alpha=0.12, color=PALETTE["strategy"],
    )

    # MDD 텍스트 박스
    textstr = (
        f"전략 MDD : {res['mdd_strategy']*100:.1f}%\n"
        f"B&H MDD  : {res['mdd_bnh']*100:.1f}%\n"
        f"매매 횟수 : {res['n_trades']}회"
    )
    ax.text(
        0.01, 0.97, textstr,
        transform=ax.transAxes,
        fontsize=9, verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.75, ec="gray"),
    )

    ax.set_title(name, fontsize=13, fontweight="bold", pad=8)
    ax.set_ylabel("누적 수익률 (%)", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:+.0f}%"))
    ax.legend(loc="upper left", fontsize=9, framealpha=0.8)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

axes2[-1].set_xlabel("날짜", fontsize=10)
plt.tight_layout()
plt.savefig("ma_crossover_backtest.png", dpi=150, bbox_inches="tight")
plt.show()
print("\n차트 저장 완료 → ma_crossover_backtest.png")