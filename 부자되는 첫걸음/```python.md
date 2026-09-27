```python
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
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

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
```

```python
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
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

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
```