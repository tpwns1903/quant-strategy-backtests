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

# ── 3. 이동평균 생성 ─────────────────────────────────────────
df["MA240"] = df["종가"].rolling(240).mean()
df["MA480"] = df["종가"].rolling(480).mean()

# ── 4. 전략 정의 ─────────────────────────────────────────────
SUPPORT_DAYS = 3

# ① 단순 돌파
df["포지션_단순_240"] = (df["종가"] > df["MA240"]).astype(int).shift(1)
df["포지션_단순_480"] = (df["종가"] > df["MA480"]).astype(int).shift(1)

# ② 돌파 + 지지: NaN을 0으로 채운 뒤 astype(int)
df["포지션_지지_240"] = (
    (df["종가"] > df["MA240"])
    .astype(float)
    .rolling(SUPPORT_DAYS).min()
    .fillna(0)
    .astype(int)
    .shift(1)
)
df["포지션_지지_480"] = (
    (df["종가"] > df["MA480"])
    .astype(float)
    .rolling(SUPPORT_DAYS).min()
    .fillna(0)
    .astype(int)
    .shift(1)
)

# ── 5. 누적 수익률 계산 ──────────────────────────────────────
def calc_cum(position):
    ret = position.fillna(0) * df["수익률"].fillna(0)  # NaN → 0 처리
    cum = (1 + ret / 100).cumprod()
    return cum

def calc_mdd(cum):
    cum = cum.replace([float("inf"), float("-inf")], float("nan")).dropna()
    return ((cum - cum.cummax()) / cum.cummax()).min() * 100

df["누적_단순_240"] = calc_cum(df["포지션_단순_240"])
df["누적_단순_480"] = calc_cum(df["포지션_단순_480"])
df["누적_지지_240"] = calc_cum(df["포지션_지지_240"])
df["누적_지지_480"] = calc_cum(df["포지션_지지_480"])
df["누적_보유"] = (1 + df["수익률"].fillna(0) / 100).cumprod()

# ── 6. 요약 출력 ─────────────────────────────────────────────
strategies = {
    "단순 돌파 MA240": df["누적_단순_240"],
    "단순 돌파 MA480": df["누적_단순_480"],
    f"돌파+지지({SUPPORT_DAYS}일) MA240": df["누적_지지_240"],
    f"돌파+지지({SUPPORT_DAYS}일) MA480": df["누적_지지_480"],
    "단순 보유":       df["누적_보유"],
}

print(f"{'전략':<25} {'최종수익률':>10} {'MDD':>10}")
print("-" * 47)
for name, cum in strategies.items():
    print(f"{name:<25} {cum.iloc[-1]:>9.3f}배 {calc_mdd(cum):>9.2f}%")

# ── 7. 시각화 ────────────────────────────────────────────────
plt.rcParams["font.family"] = (
    "AppleGothic"
    if "AppleGothic" in [f.name for f in fm.fontManager.ttflist]
    else "NanumGothic"
)
plt.rcParams["axes.unicode_minus"] = False

fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

# 상단: MA240 비교
axes[0].plot(df.index, df["누적_단순_240"],            label="단순 돌파",               linewidth=1.5)
axes[0].plot(df.index, df["누적_지지_240"],            label=f"돌파+지지({SUPPORT_DAYS}일)", linewidth=1.5)
axes[0].plot(df.index, df["누적_보유"],                label="단순 보유", linewidth=1.2, alpha=0.5, linestyle="--")
axes[0].set_title("MA240 단순 돌파 vs 돌파+지지")
axes[0].legend()
axes[0].grid(True, alpha=0.3)
axes[0].set_ylabel("누적 수익률 (배)")

# 하단: MA480 비교
axes[1].plot(df.index, df["누적_단순_480"],            label="단순 돌파",               linewidth=1.5)
axes[1].plot(df.index, df["누적_지지_480"],            label=f"돌파+지지({SUPPORT_DAYS}일)", linewidth=1.5)
axes[1].plot(df.index, df["누적_보유"],                label="단순 보유", linewidth=1.2, alpha=0.5, linestyle="--")
axes[1].set_title("MA480 단순 돌파 vs 돌파+지지")
axes[1].legend()
axes[1].grid(True, alpha=0.3)
axes[1].set_ylabel("누적 수익률 (배)")
axes[1].set_xlabel("날짜")

plt.tight_layout()
plt.show()