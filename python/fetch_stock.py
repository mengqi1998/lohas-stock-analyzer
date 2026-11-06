
import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests

# 第一階段先測試台積電
STOCK_ID = "2330"

# 往前抓約五年的資料，確保有足夠交易日進行滾動迴歸
END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=1800)

API_URL = "https://api.finmindtrade.com/api/v4/data"

def fetch_stock_price(stock_id):
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
    }

    headers = {}
    token = os.getenv("FINMIND_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(
        API_URL,
        params=params,
        headers=headers,
        timeout=60
    )
    
    # 先取得 API 回應內容，再判斷是否成功
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            f"FinMind 回傳非 JSON 格式：HTTP {response.status_code}\n"
            f"{response.text[:1000]}"
        )
    
    if response.status_code != 200:
        raise RuntimeError(
            f"FinMind HTTP 錯誤：{response.status_code}\n"
            f"API 回應：{result}"
        )
    
    if result.get("status") != 200:
        raise RuntimeError(
            f"FinMind API 錯誤：{result.get('msg')}\n"
            f"完整回應：{result}"
        )


    records = result.get("data", [])

    if not records:
        raise RuntimeError(f"{stock_id} 沒有取得股價資料")

    # 依日期排序
    records.sort(key=lambda x: x["date"])

    output = {
        "stock_id": stock_id,
        "dataset": "TaiwanStockPrice",
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
        "latest_date": records[-1]["date"],
        "record_count": len(records),
        "data": records
    }

    output_dir = Path("data/prices")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{stock_id}.json"

    output_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"成功下載：{stock_id}")
    print(f"資料筆數：{len(records)}")
    print(f"最新日期：{records[-1]['date']}")
    print(f"儲存位置：{output_file}")



def fetch_stock_fundamental(stock_id):
    """取得個股最新 PER、PBR 與殖利率，另存為前端可讀的 JSON。"""
    params = {
        "dataset": "TaiwanStockPER",
        "data_id": stock_id,
        "start_date": (END_DATE - timedelta(days=45)).isoformat(),
        "end_date": END_DATE.isoformat(),
    }

    headers = {}
    token = os.getenv("FINMIND_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(API_URL, params=params, headers=headers, timeout=60)
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            f"FinMind 基本面資料回傳非 JSON：HTTP {response.status_code}"
        )

    if response.status_code != 200 or result.get("status") != 200:
        raise RuntimeError(
            f"FinMind 基本面 API 錯誤：HTTP {response.status_code}；{result}"
        )

    records = result.get("data", [])
    records.sort(key=lambda item: item.get("date", ""))

    if records:
        latest = records[-1]
        fundamental = {
            "date": latest.get("date"),
            "PER": latest.get("PER"),
            "PBR": latest.get("PBR"),
            "dividend_yield": latest.get("dividend_yield"),
        }
        status = "success"
        message = None
    else:
        fundamental = {
            "date": None, "PER": None, "PBR": None, "dividend_yield": None
        }
        status = "no_data"
        message = "FinMind 目前沒有回傳此標的的個股 PER/PBR 資料。"

    output = {
        "stock_id": stock_id,
        "asset_type": "stock",
        "source": "FinMind TaiwanStockPER",
        "status": status,
        "message": message,
        "data": fundamental,
    }

    output_dir = Path("data/fundamentals")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{stock_id}.json"
    output_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"基本面資料狀態：{status}")
    print(f"基本面資料日期：{fundamental['date']}")
    print(f"基本面儲存位置：{output_file}")


if __name__ == "__main__":
    fetch_stock_price(STOCK_ID)
    fetch_stock_fundamental(STOCK_ID)
