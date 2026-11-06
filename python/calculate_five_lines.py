
import json
from pathlib import Path

import numpy as np
import pandas as pd


# =========================
# 基本設定
# =========================

STOCK_ID = "2330"
WINDOW = 500

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = BASE_DIR / "data" / "prices" / f"{STOCK_ID}.json"
OUTPUT_DIR = BASE_DIR / "data" / "five_lines"
OUTPUT_FILE = OUTPUT_DIR / f"{STOCK_ID}.json"


def main():

    # =========================
    # 讀取資料
    # =========================

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"找不到股價資料：{INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    records = raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data

    if not records:
        raise ValueError("股價資料為空，無法計算")

    df = pd.DataFrame(records)

    required_columns = {"date", "close"}

    if not required_columns.issubset(df.columns):
        raise ValueError(
            f"缺少必要欄位：{required_columns - set(df.columns)}"
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = (
        df.dropna(subset=["date", "close"])
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .tail(WINDOW)
        .reset_index(drop=True)
    )

    actual_days = len(df)

    # =========================
    # 資料不足處理
    # =========================

    if actual_days < WINDOW:

        result = {
            "stock_id": STOCK_ID,
            "window": WINDOW,
            "actual_days": actual_days,
            "status": "insufficient_data",
            "message": (
                f"資料不足，需要 {WINDOW} 個交易日，"
                f"目前只有 {actual_days} 個交易日。"
            ),
            "data": []
        }

    else:

        # =========================
        # 線性迴歸與五線譜
        # =========================

        x = np.arange(actual_days)

        y = df["close"].to_numpy(dtype=float)

        slope, intercept = np.polyfit(x, y, 1)

        trend = slope * x + intercept

        residuals = y - trend

        sigma = float(np.std(residuals, ddof=0))

        df["trend"] = trend
        df["upper_1"] = trend + sigma
        df["lower_1"] = trend - sigma
        df["upper_2"] = trend + 2 * sigma
        df["lower_2"] = trend - 2 * sigma

        # =========================
        # 買進 / 賣出觀察訊號
        # =========================

        df["buy_signal"] = False
        df["sell_signal"] = False
        df["signal"] = "none"

        for i in range(1, actual_days):

            previous_close = df.loc[i - 1, "close"]
            current_close = df.loc[i, "close"]

            previous_lower = df.loc[i - 1, "lower_2"]
            current_lower = df.loc[i, "lower_2"]

            previous_upper = df.loc[i - 1, "upper_2"]
            current_upper = df.loc[i, "upper_2"]

            # 買進觀察：
            # 前一天收盤價在下下線以下
            # 今天收盤價重新回到下下線之上

            if (
                previous_close < previous_lower
                and current_close >= current_lower
            ):

                df.loc[i, "buy_signal"] = True
                df.loc[i, "signal"] = "buy"

            # 賣出觀察：
            # 前一天收盤價在上上線以上
            # 今天收盤價重新回到上上線之下

            elif (
                previous_close > previous_upper
                and current_close <= current_upper
            ):

                df.loc[i, "sell_signal"] = True
                df.loc[i, "signal"] = "sell"

        # =========================
        # 整理輸出資料
        # =========================

        output_data = []

        for _, row in df.iterrows():

            output_data.append({

                "date": row["date"].strftime("%Y-%m-%d"),

                "close": round(float(row["close"]), 2),

                "trend": round(float(row["trend"]), 2),

                "upper_1": round(float(row["upper_1"]), 2),

                "lower_1": round(float(row["lower_1"]), 2),

                "upper_2": round(float(row["upper_2"]), 2),

                "lower_2": round(float(row["lower_2"]), 2),

                "buy_signal": bool(row["buy_signal"]),

                "sell_signal": bool(row["sell_signal"]),

                "signal": row["signal"]

            })

        result = {

            "stock_id": STOCK_ID,

            "window": WINDOW,

            "actual_days": actual_days,

            "status": "success",

            "sigma": round(sigma, 4),

            "slope": round(float(slope), 6),

            "intercept": round(float(intercept), 4),

            "latest_signal": output_data[-1]["signal"],

            "data": output_data

        }

    # =========================
    # 儲存 JSON
    # =========================

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("五線譜計算完成")
    print(f"股票代號：{STOCK_ID}")
    print(f"資料筆數：{actual_days}")
    print(f"狀態：{result['status']}")

    if result["status"] == "success":

        print(f"最新訊號：{result['latest_signal']}")

        buy_count = sum(
            item["buy_signal"] for item in result["data"]
        )

        sell_count = sum(
            item["sell_signal"] for item in result["data"]
        )

        print(f"買進觀察訊號數量：{buy_count}")
        print(f"賣出觀察訊號數量：{sell_count}")

    print(f"輸出位置：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
