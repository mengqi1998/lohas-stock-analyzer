
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



def request_finmind_dataset(dataset, stock_id, start_date):
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
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
        raise RuntimeError(f"{dataset} 回傳非 JSON：HTTP {response.status_code}")

    if response.status_code != 200 or result.get("status") != 200:
        raise RuntimeError(f"{dataset} API 錯誤：HTTP {response.status_code}；{result}")

    return result.get("data", [])


def fetch_stock_fundamental(stock_id):
    """取得個股估值、EPS 與月營收摘要。"""
    start_date = (END_DATE - timedelta(days=900)).isoformat()

    per_rows = request_finmind_dataset(
        "TaiwanStockPER", stock_id,
        (END_DATE - timedelta(days=45)).isoformat()
    )
    statement_rows = request_finmind_dataset(
        "TaiwanStockFinancialStatements", stock_id, start_date
    )
    revenue_rows = request_finmind_dataset(
        "TaiwanStockMonthRevenue", stock_id, start_date
    )

    per_rows.sort(key=lambda row: row.get("date", ""))
    statement_rows.sort(key=lambda row: row.get("date", ""))
    revenue_rows.sort(key=lambda row: row.get("date", ""))

    latest_per = per_rows[-1] if per_rows else {}
    eps_rows = [
        row for row in statement_rows
        if row.get("type") == "EPS" and row.get("value") is not None
    ]
    eps_rows.sort(key=lambda row: row.get("date", ""))
    report_dates = sorted({row.get("date") for row in eps_rows if row.get("date")})
    latest_eps = None
    ttm_eps = None
    eps_date = None
    if report_dates:
        eps_date = report_dates[-1]
        latest_eps_values = [
            row.get("value") for row in eps_rows if row.get("date") == eps_date
        ]
        if latest_eps_values:
            latest_eps = float(latest_eps_values[-1])
        last_four_dates = report_dates[-4:]
        ttm_values = []
        for report_date in last_four_dates:
            matches = [
                row.get("value") for row in eps_rows
                if row.get("date") == report_date
            ]
            if matches:
                ttm_values.append(float(matches[-1]))
        if len(last_four_dates) == 4 and len(ttm_values) == 4:
            ttm_eps = sum(ttm_values)

    latest_revenue = revenue_rows[-1] if revenue_rows else {}
    revenue_value = latest_revenue.get("revenue")
    revenue_yoy = None
    if latest_revenue:
        try:
            this_year = int(latest_revenue.get("revenue_year"))
            this_month = int(latest_revenue.get("revenue_month"))
            previous_year_rows = [
                row for row in revenue_rows
                if int(row.get("revenue_year", -1)) == this_year - 1
                and int(row.get("revenue_month", -1)) == this_month
            ]
            if previous_year_rows:
                previous_revenue = float(previous_year_rows[-1].get("revenue"))
                if previous_revenue:
                    revenue_yoy = (
                        (float(revenue_value) - previous_revenue)
                        / previous_revenue * 100
                    )
        except (TypeError, ValueError):
            revenue_yoy = None

    fundamental = {
        "date": latest_per.get("date"),
        "PER": latest_per.get("PER"),
        "PBR": latest_per.get("PBR"),
        "dividend_yield": latest_per.get("dividend_yield"),
        "latest_quarter_EPS": latest_eps,
        "EPS_date": eps_date,
        "TTM_EPS": ttm_eps,
        "revenue": revenue_value,
        "revenue_date": latest_revenue.get("date"),
        "revenue_yoy": revenue_yoy,
    }

    has_any_data = any(value is not None for value in fundamental.values())
    output = {
        "stock_id": stock_id,
        "asset_type": "stock",
        "source": "FinMind TaiwanStockPER / TaiwanStockFinancialStatements / TaiwanStockMonthRevenue",
        "status": "success" if has_any_data else "no_data",
        "message": None if has_any_data else "目前沒有可用的個股基本面資料。",
        "data": fundamental,
    }

    output_dir = Path("data/fundamentals")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{stock_id}.json"
    output_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"基本面資料狀態：{output['status']}")
    print(f"估值資料日期：{fundamental['date']}")
    print(f"EPS 資料日期：{fundamental['EPS_date']}")
    print(f"營收資料日期：{fundamental['revenue_date']}")
    print(f"基本面儲存位置：{output_file}")


if __name__ == "__main__":
    fetch_stock_price(STOCK_ID)
    fetch_stock_fundamental(STOCK_ID)
