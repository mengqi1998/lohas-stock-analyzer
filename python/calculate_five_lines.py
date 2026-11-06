
import json
import os
import numpy as np
import pandas as pd

STOCK_ID = "2330"
WINDOW = 500
OUTPUT_DAYS = 500

PRICE_FILE = f"data/prices/{STOCK_ID}.json"
OUTPUT_FILE = f"data/five_lines/{STOCK_ID}.json"


def load_price_data():
    if not os.path.exists(PRICE_FILE):
        raise FileNotFoundError(f"找不到股價資料：{PRICE_FILE}")

    with open(PRICE_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # 支援 API 常見的 {"data": [...]} 格式
    if isinstance(raw, dict):
        records = raw.get("data", [])
    elif isinstance(raw, list):
        records = raw
    else:
        records = []

    df = pd.DataFrame(records)

    if df.empty:
        raise ValueError("股價資料是空的")

    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError("股價資料缺少 date 或 close 欄位")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = df.dropna(subset=["date", "close"])
    df = df[df["close"] > 0]

    df = (
        df.sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )

    return df


def calculate_rolling_five_lines(df):
    results = []

    # 每一天都只使用當天及之前的 500 個交易日
    for end_idx in range(WINDOW - 1, len(df)):
        start_idx = end_idx - WINDOW + 1

        window_df = df.iloc[start_idx:end_idx + 1]

        y = window_df["close"].to_numpy(dtype=float)
        x = np.arange(WINDOW, dtype=float)

        # 線性迴歸：trend = slope * x + intercept
        slope, intercept = np.polyfit(x, y, 1)

        trend_values = slope * x + intercept
        residuals = y - trend_values

        # 母體標準差
        sigma = float(np.std(residuals, ddof=0))

        # 只取當日（迴歸區間最後一天）的趨勢線數值
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
        })

    # 以相鄰兩個交易日各自的五線譜判斷穿越訊號
    for i in range(1, len(results)):
        previous = results[i - 1]
        current = results[i]

        # 買進觀察：
        # 前一日收盤低於前一日下下線，
        # 當日收盤回到當日下下線之上或相等
        if (
            previous["close"] < previous["lower_2"]
            and current["close"] >= current["lower_2"]
        ):
            current["buy_signal"] = True
            current["signal"] = "buy"

        # 賣出觀察：
        # 前一日收盤高於前一日上上線，
        # 當日收盤回到當日上上線之下或相等
        elif (
            previous["close"] > previous["upper_2"]
            and current["close"] <= current["upper_2"]
        ):
            current["sell_signal"] = True
            current["signal"] = "sell"

    return results


def main():
    df = load_price_data()

    all_results = calculate_rolling_five_lines(df)

    # 只保留最近 500 個有效計算日
    results = all_results[-OUTPUT_DAYS:]

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    if len(results) < OUTPUT_DAYS:
        output = {
            "stock_id": STOCK_ID,
            "window": WINDOW,
            "actual_days": len(results),
            "raw_days": len(df),
            "status": "insufficient_data",
            "message": (
                f"需要至少 {WINDOW + OUTPUT_DAYS - 1} 個原始交易日，"
                f"目前只有 {len(df)} 個原始交易日，"
                f"可計算 {len(results)} 個有效日期。"
            ),
            "sigma": None,
            "slope": round(latest["slope"], 8),
            "intercept": round(latest["intercept"], 8),
            "latest_signal": "none",
            "data": [],
        }
    else:
        latest = results[-1]

        output = {
            "stock_id": STOCK_ID,
            "window": WINDOW,
            "actual_days": len(results),
            "raw_days": len(df),
            "status": "success",
            "calculation_method": "rolling_linear_regression",
            "sigma": round(
                (latest["upper_1"] - latest["trend"]), 4
            ),
            "slope": None,
            "intercept": None,
            "latest_signal": latest["signal"],
            "data": [
                {
                    **row,
                    "close": round(row["close"], 4),
                    "trend": round(row["trend"], 4),
                    "upper_1": round(row["upper_1"], 4),
                    "lower_1": round(row["lower_1"], 4),
                    "upper_2": round(row["upper_2"], 4),
                    "lower_2": round(row["lower_2"], 4),
                }
                for row in results
            ],
        }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"股票代號：{STOCK_ID}")
    print(f"原始交易日數：{len(df)}")
    print(f"有效計算日數：{len(results)}")
    print(f"資料狀態：{output['status']}")
    print(f"最新訊號：{output['latest_signal']}")
    print(f"輸出位置：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
