import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 날짜 범위 설정 (최근 10년)
end_date = datetime.today()
start_date = end_date - timedelta(days=365 * 10)

# KOSPI 데이터 다운로드 (티커: ^KS11)
ticker = yf.Ticker("^KS11")
df_raw = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                        end=end_date.strftime("%Y-%m-%d"))

# 필요한 컬럼만 선택 및 인덱스 정리
df = df_raw[["Close"]].copy()
df.index = pd.to_datetime(df.index).tz_localize(None)  # 타임존 제거
df.index.name = "날짜"
df.columns = ["종가"]

# 결측값 처리 (앞값으로 채운 뒤 남은 결측값은 제거)
df["종가"] = df["종가"].ffill().dropna()

# 일별 수익률 계산 (%)
df["수익률"] = df["종가"].pct_change() * 100

# 첫 번째 행 수익률은 NaN → 제거
df = df.dropna(subset=["수익률"])

print(df.shape)
print(df.head())
print(df.tail())

# 이동평균 계산
df['MA20'] = df['종가'].rolling(20).mean()
df['MA60'] = df['종가'].rolling(60).mean()

# 포지션 (미래 데이터 방지: shift(1))
df['포지션'] = (df['MA20'] > df['MA60']).astype(int).shift(1)

# 전략 수익률
df['전략수익률'] = df['포지션'] * df['수익률']

# 누적 수익률
df['누적_전략'] = (1 + df['전략수익률'] / 100).cumprod()
df['누적_보유'] = (1 + df['수익률'] / 100).cumprod()

# 그래프


plt.rcParams['font.family'] = 'AppleGothic' if 'AppleGothic' in [f.name for f in fm.fontManager.ttflist] else 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(df.index, df['누적_전략'], label='MA 전략', linewidth=1.5)
ax.plot(df.index, df['누적_보유'], label='단순 보유', linewidth=1.5, alpha=0.7)
ax.set_title('KOSPI 이동평균 전략 vs 단순 보유 (누적 수익률)')
ax.set_xlabel('날짜')
ax.set_ylabel('누적 수익률 (배)')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# 요약 출력
print(f"전략 최종 수익률: {df['누적_전략'].iloc[-1]:.3f}배")
print(f"단순보유 최종 수익률: {df['누적_보유'].iloc[-1]:.3f}배")

