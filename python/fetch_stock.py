
import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests

# 第一階段先測試台積電
STOCK_ID = "2330"

# 往前抓約兩年的資料，足以涵蓋 500 個交易日
END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=800)

API_URL = "https://api.finmindtrade.com/api/v4/data"

def fetch_stock_price(stock_id):
    params = {
        "dataset": "TaiwanStockPriceAdj",
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
    response.raise_for_status()

    result = response.json()

    if result.get("status") != 200:
        raise RuntimeError(
            f"FinMind API 錯誤：{result.get('msg')}"
        )

    records = result.get("data", [])

    if not records:
        raise RuntimeError(f"{stock_id} 沒有取得股價資料")

    # 依日期排序
    records.sort(key=lambda x: x["date"])

    output = {
        "stock_id": stock_id,
        "dataset": "TaiwanStockPriceAdj",
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


if __name__ == "__main__":
    fetch_stock_price(STOCK_ID)
