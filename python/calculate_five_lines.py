
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
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"找不到股價資料：{INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # FinMind API 回傳格式通常為 {"data": [...]}
    records = raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data

    if not records:
        raise ValueError("股價資料為空，無法計算")

    df = pd.DataFrame(records)

    required_columns = {"date", "close"}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"缺少必要欄位：{required_columns - set(df.columns)}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = (
        df.dropna(subset=["date", "close"])
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .tail(WINDOW)
        .reset_index(drop=True)
    )

    if len(df) < WINDOW:
        result = {
            "stock_id": STOCK_ID,
            "window": WINDOW,
            "actual_days": len(df),
            "status": "insufficient_data",
            "message": f"資料不足，需要 {WINDOW} 個交易日，目前只有 {len(df)} 個交易日。",
            "data": []
        }
    else:
        # 以交易日序號作為 X 軸
        x = np.arange(len(df))
        y = df["close"].to_numpy(dtype=float)

        # 一次線性迴歸：y = slope * x + intercept
        slope, intercept = np.polyfit(x, y, 1)
        trend = slope * x + intercept

        # 殘差標準差（母體標準差）
        residuals = y - trend
        sigma = float(np.std(residuals, ddof=0))

        df["trend"] = trend
        df["upper_1"] = trend + sigma
        df["lower_1"] = trend - sigma
        df["upper_2"] = trend + 2 * sigma
        df["lower_2"] = trend - 2 * sigma

        output_data = []

        for _, row in df.iterrows():
            output_data.append({
                "date": row["date"].strftime("%Y-%m-%d"),
                "close": round(float(row["close"]), 2),
                "trend": round(float(row["trend"]), 2),
                "upper_1": round(float(row["upper_1"]), 2),
                "lower_1": round(float(row["lower_1"]), 2),
                "upper_2": round(float(row["upper_2"]), 2),
                "lower_2": round(float(row["lower_2"]), 2)
            })

        result = {
            "stock_id": STOCK_ID,
            "window": WINDOW,
            "actual_days": len(df),
            "status": "success",
            "sigma": round(sigma, 4),
            "slope": round(float(slope), 6),
            "intercept": round(float(intercept), 4),
            "data": output_data
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"五線譜計算完成：{OUTPUT_FILE}")
    print(f"狀態：{result['status']}")
    print(f"資料筆數：{result['actual_days']}")


if __name__ == "__main__":
    main()

