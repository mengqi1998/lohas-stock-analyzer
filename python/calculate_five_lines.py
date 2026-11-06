import json
import os

import numpy as np
import pandas as pd

STOCK_IDS = ["2330", "0050"]
WINDOW = 500
OUTPUT_DAYS = 500


def load_price_data(stock_id):
    price_file = f"data/prices/{stock_id}.json"
    if not os.path.exists(price_file):
        raise FileNotFoundError(f"找不到股價資料：{price_file}")

    with open(price_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = raw.get("data", []) if isinstance(raw, dict) else raw
    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError(f"{stock_id} 股價資料是空的")
    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError(f"{stock_id} 股價資料缺少 date 或 close 欄位")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    df = df[df["close"] > 0]
    return (
        df.sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )


def calculate_rolling_five_lines(df):
    results = []
    for end_idx in range(WINDOW - 1, len(df)):
        start_idx = end_idx - WINDOW + 1
        window_df = df.iloc[start_idx:end_idx + 1]
        y = window_df["close"].to_numpy(dtype=float)
        x = np.arange(WINDOW, dtype=float)

        slope, intercept = np.polyfit(x, y, 1)
        trend_values = slope * x + intercept
        residuals = y - trend_values
        sigma = float(np.std(residuals, ddof=0))

        current_trend = float(slope * (WINDOW - 1) + intercept)
        current_close = float(df.loc[end_idx, "close"])
        results.append({
            "date": df.loc[end_idx, "date"].strftime("%Y-%m-%d"),
            "close": current_close,
            "trend": current_trend,
            "upper_1": current_trend + sigma,
            "lower_1": current_trend - sigma,
            "upper_2": current_trend + 2 * sigma,
            "lower_2": current_trend - 2 * sigma,
            "buy_signal": False,
            "sell_signal": False,
            "signal": "none",
            "slope": float(slope),
            "intercept": float(intercept),
            "sigma": sigma,
        })

    for i in range(1, len(results)):
        previous = results[i - 1]
        current = results[i]
        if (
            previous["close"] < previous["lower_2"]
            and current["close"] >= current["lower_2"]
        ):
            current["buy_signal"] = True
            current["signal"] = "buy"
        elif (
            previous["close"] > previous["upper_2"]
            and current["close"] <= current["upper_2"]
        ):
            current["sell_signal"] = True
            current["signal"] = "sell"
    return results


def main():
    for stock_id in STOCK_IDS:
        df = load_price_data(stock_id)
        all_results = calculate_rolling_five_lines(df)
        results = all_results[-OUTPUT_DAYS:]
        output_file = f"data/five_lines/{stock_id}.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        latest = results[-1] if results else None
        status = "success" if len(results) == OUTPUT_DAYS else "insufficient_data"

        output = {
            "stock_id": stock_id,
            "window": WINDOW,
            "actual_days": len(results),
            "raw_days": len(df),
            "status": status,
            "message": None if status == "success" else (
                f"需要至少 {WINDOW + OUTPUT_DAYS - 1} 個原始交易日；"
                f"目前有 {len(df)} 筆原始資料，可計算 {len(results)} 天。"
            ),
            "calculation_method": "rolling_linear_regression",
            "sigma": round(latest["sigma"], 4) if latest else None,
            "slope": round(latest["slope"], 8) if latest else None,
            "intercept": round(latest["intercept"], 8) if latest else None,
            "latest_signal": latest["signal"] if latest else "none",
            "data": [
                {
                    **row,
                    "close": round(row["close"], 4),
                    "trend": round(row["trend"], 4),
                    "upper_1": round(row["upper_1"], 4),
                    "lower_1": round(row["lower_1"], 4),
                    "upper_2": round(row["upper_2"], 4),
                    "lower_2": round(row["lower_2"], 4),
                    "slope": round(row["slope"], 8),
                    "intercept": round(row["intercept"], 8),
                    "sigma": round(row["sigma"], 4),
                }
                for row in results
            ] if status == "success" else [],
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"股票代號：{stock_id}")
        print(f"原始交易日數：{len(df)}")
        print(f"有效計算日數：{len(results)}")
        print(f"資料狀態：{status}")
        print(f"最新訊號：{output['latest_signal']}")
        print(f"最新斜率：{output['slope']}")
        print(f"最新截距：{output['intercept']}")
        print(f"輸出位置：{output_file}")


if __name__ == "__main__":
    main()
