"""
README 성과 비교표 재현 스크립트
──────────────────────────────────
각 단계의 백테스트 스크립트를 수정 없이 실행한 뒤, 일별 자산곡선에
같은 공식으로 CAGR / MDD / 샤프 비율을 계산해 JSON으로 출력한다.

  CAGR  : 최종배수 ^ (1 / 달력 연수) - 1
  MDD   : 고점 대비 최대 낙폭
  샤프  : 일간 수익률 평균 / 표준편차 × √252 (무위험수익률 0)

사용법:
  python compute_metrics.py 01 02 03     # 지수 기반 단계 (수 분)
  python compute_metrics.py 04a          # KOSPI 200 모멘텀 (종목 다운로드, 수 분)
  python compute_metrics.py 04b          # KOSDAQ 150 모멘텀
  ※ 04 스크립트는 실행 시 sys.stdout을 교체하므로 04a / 04b는 따로 실행한다.
"""

import json
import os
import runpy
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.show = lambda *a, **k: None
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
steps = sys.argv[1:] or ["01", "02", "03"]


def metrics(equity: pd.Series) -> dict:
    eq = equity.dropna()
    eq = eq / eq.iloc[0]
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    rets = eq.pct_change().dropna()
    return {
        "period": f"{eq.index[0].date()} ~ {eq.index[-1].date()}",
        "total_%": round((eq.iloc[-1] - 1) * 100, 2),
        "cagr_%": round((eq.iloc[-1] ** (1 / years) - 1) * 100, 2),
        "mdd_%": round((eq / eq.cummax() - 1).min() * 100, 2),
        "sharpe": round(rets.mean() / rets.std() * np.sqrt(252), 2) if rets.std() > 0 else 0.0,
    }


def run(rel_path):
    path = os.path.join(ROOT, rel_path)
    os.chdir(os.path.dirname(path))
    g = runpy.run_path(path, run_name="compute_metrics")
    plt.close("all")
    return g


out = {}

if "01" in steps:
    df = run("01_moving_average_basics/ma_crossover_20_60.py")["df"]
    out["01 MA20/60 교차"] = metrics(df["누적_전략"])
    out["01 Buy & Hold (KOSPI)"] = metrics(df["누적_보유"])
    df = run("01_moving_average_basics/ma_trend_volatility_filter.py")["df"]
    out["01 MA + 추세/변동성 필터"] = metrics(df["누적_전략"])
    df = run("01_moving_average_basics/long_term_ma_240_480.py")["df"]
    for col, label in [("누적_단순_240", "MA240 단순 돌파"), ("누적_지지_240", "MA240 돌파+지지"),
                       ("누적_단순_480", "MA480 단순 돌파"), ("누적_지지_480", "MA480 돌파+지지")]:
        out[f"01 {label}"] = metrics(df[col])

if "02" in steps:
    g = run("02_index_ma_crossover/kospi_kosdaq_ma_crossover.py")
    for name, res in g["results"].items():
        out[f"02 MA20/60 교차 ({name})"] = metrics(res["bt"]["cum_strategy"])
        out[f"02 Buy & Hold ({name})"] = metrics(res["bt"]["cum_bnh"])

if "03" in steps:
    g = run("03_improved_ma_strategy/improved_ma_pyramiding.py")
    for name, df in g["dfs"].items():
        r = g["pyramid_results"][name]
        out[f"03 MA20/60 교차 ({name})"] = metrics(g["run_old_strategy"](df)["cum_strat"])
        out[f"03 개선 전략 ({name})"] = metrics(r["base_bt"]["equity"])
        out[f"03 피라미딩 ({name})"] = metrics(r["pyr_bt"]["equity"])
        out[f"03 Buy & Hold ({name})"] = metrics(r["pyr_bt"]["cum_bnh"])

if "04a" in steps:
    g = run("04_momentum_portfolio/kospi200_momentum.py")
    sc, so, sh, sl, idx_close, idx_open, valid = g["download_data"](
        g["KOSPI_TOP50_TICKERS"], g["START_DATE"], g["END_DATE"])
    daily, dates, log, _ = g["run_backtest"](valid, sc, so, sh, sl, idx_close, idx_open)
    out["04 KOSPI 200 모멘텀"] = metrics((1 + pd.Series(daily, index=dates)).cumprod())
    out["04 Buy & Hold (KOSPI)"] = metrics(idx_close.reindex(dates).ffill())

if "04b" in steps:
    g = run("04_momentum_portfolio/kosdaq150_momentum.py")
    sc, so, sh, sl, idx_close, valid = g["download_data"](
        g["KOSDAQ_TICKERS"], g["START_DATE"], g["END_DATE"])
    ind = g["compute_indicators"](sc, so, sh, sl)
    daily, dates, log, _ = g["run_backtest"](valid, sc, so, sh, sl, *ind)
    out["04 KOSDAQ 150 모멘텀"] = metrics((1 + pd.Series(daily, index=dates)).cumprod())
    out["04 Buy & Hold (KOSDAQ)"] = metrics(idx_close.reindex(dates).ffill())

result_path = os.path.join(ROOT, f"metrics_{'_'.join(steps)}.json")
with open(result_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"\n저장 완료 → {result_path}")
