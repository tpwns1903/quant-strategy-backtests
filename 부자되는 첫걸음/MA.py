import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import datetime, timedelta

# ── 1. 데이터 수집 ──────────────────────────────────────────
end_date   = datetime.today()
start_date = end_date - timedelta(days=365 * 10)

ticker = yf.Ticker("^KS11")
df_raw = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                        end=end_date.strftime("%Y-%m-%d"))

df = df_raw[["Close"]].copy()
df.index = pd.to_datetime(df.index).tz_localize(None)
df.index.name = "날짜"
df.columns = ["종가"]

# ── 2. 결측값 처리 & 수익률 ─────────────────────────────────
df["종가"]   = df["종가"].ffill()
df["수익률"] = df["종가"].pct_change() * 100
df = df.dropna(subset=["수익률"])

# ── 3. 지표 생성 ─────────────────────────────────────────────
df["MA20"]           = df["종가"].rolling(20).mean()
df["MA60"]           = df["종가"].rolling(60).mean()
df["trend_strength"] = df["수익률"].rolling(20).sum()
df["변동성"]          = df["수익률"].rolling(20).std()

vol_threshold = df["변동성"].mean() * 0.7

# ── 4. 조건 & 포지션 ─────────────────────────────────────────
ma_signal    = df["MA20"] > df["MA60"]
trend_signal = df["trend_strength"] > 0
vol_signal   = df["변동성"] > vol_threshold

df["포지션"] = 0.0
df.loc[ma_signal,                             "포지션"] = 0.5
df.loc[ma_signal & trend_signal & vol_signal, "포지션"] = 1.0
df["포지션"] = df["포지션"].shift(1)

# ── 5. 전략 수익률 & 누적 수익률 ────────────────────────────
df["전략수익률"] = df["포지션"] * df["수익률"]
df["누적_전략"]  = (1 + df["전략수익률"] / 100).cumprod()
df["누적_보유"]  = (1 + df["수익률"] / 100).cumprod()

# ── 6. MDD 계산 ──────────────────────────────────────────────
def calc_mdd(cum):
    return ((cum - cum.cummax()) / cum.cummax()).min() * 100

mdd_전략 = calc_mdd(df["누적_전략"])
mdd_보유  = calc_mdd(df["누적_보유"])

# ── 7. 포지션 분포 ───────────────────────────────────────────
print("=== 포지션 분포 ===")
print(df["포지션"].value_counts().sort_index())

# ── 8. 요약 ──────────────────────────────────────────────────
print(f"\n전략 최종 수익률:     {df['누적_전략'].iloc[-1]:.3f}배")
print(f"단순보유 최종 수익률: {df['누적_보유'].iloc[-1]:.3f}배")
print(f"전략 MDD:             {mdd_전략:.2f}%")
print(f"단순보유 MDD:         {mdd_보유:.2f}%")

# ── 9. 시각화 ────────────────────────────────────────────────
plt.rcParams["font.family"] = (
    "AppleGothic"
    if "AppleGothic" in [f.name for f in fm.fontManager.ttflist]
    else "NanumGothic"
)
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(df.index, df["누적_전략"], label="포지션 사이징 전략", linewidth=1.5)
ax.plot(df.index, df["누적_보유"], label="단순 보유",          linewidth=1.5, alpha=0.7)
ax.set_title("KOSPI 포지션 사이징 전략 vs 단순 보유")
ax.set_xlabel("날짜")
ax.set_ylabel("누적 수익률 (배)")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()