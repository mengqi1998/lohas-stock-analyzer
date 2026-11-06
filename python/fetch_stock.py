import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests

# 先以一檔個股與一檔 ETF 驗證完整流程。
# 要增加標的時，將代號加入這個清單即可。
STOCK_IDS = ["2330", "0050"]

END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=1800)
API_URL = "https://api.finmindtrade.com/api/v4/data"


def finmind_request(dataset, stock_id=None, start_date=None):
    params = {"dataset": dataset}
    if stock_id:
        params["data_id"] = stock_id
    if start_date:
        params["start_date"] = start_date
        params["end_date"] = END_DATE.isoformat()

    headers = {}
    token = os.getenv("FINMIND_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(API_URL, params=params, headers=headers, timeout=90)
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(f"{dataset} 回傳非 JSON：HTTP {response.status_code}")

    if response.status_code != 200 or result.get("status") != 200:
        raise RuntimeError(
            f"{dataset} API 錯誤：HTTP {response.status_code}；{result}"
        )
    return result.get("data", [])


def latest_record(records):
    if not records:
        return {}
    return sorted(records, key=lambda row: row.get("date", ""))[-1]


def value_for(records, *types):
    for item_type in types:
        matches = [
            row for row in records
            if row.get("type") == item_type and row.get("value") is not None
        ]
        if matches:
            return float(latest_record(matches)["value"])
    return None


def safe_ratio(numerator, denominator, multiplier=1):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * multiplier


def get_stock_catalog():
    rows = finmind_request("TaiwanStockInfo")
    catalog = {}
    for row in rows:
        stock_id = str(row.get("stock_id", "")).strip()
        if stock_id:
            catalog[stock_id] = row
    return catalog


def fetch_stock_price(stock_id):
    records = finmind_request(
        "TaiwanStockPrice", stock_id, START_DATE.isoformat()
    )
    if not records:
        raise RuntimeError(f"{stock_id} 沒有取得股價資料")

    records.sort(key=lambda row: row["date"])
    output = {
        "stock_id": stock_id,
        "dataset": "TaiwanStockPrice",
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
        "latest_date": records[-1]["date"],
        "record_count": len(records),
        "data": records,
    }
    output_dir = Path("data/prices")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{stock_id}.json"
    output_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{stock_id} 股價：{len(records)} 筆，最新日期 {records[-1]['date']}")


def fetch_stock_fundamental(stock_id, catalog):
    info = catalog.get(stock_id, {})
    asset_type = (
        "etf" if info.get("industry_category") == "ETF" else "stock"
    )
    stock_name = info.get("stock_name", stock_id)
    start_date = (END_DATE - timedelta(days=1100)).isoformat()

    output_data = {
        "date": None,
        "PER": None,
        "PBR": None,
        "dividend_yield": None,
        "latest_quarter_EPS": None,
        "EPS_date": None,
        # 不直接加總 FinMind 各季 EPS；配股、分割可能令跨季 EPS 基準不一致。
        "TTM_EPS": None,
        "TTM_EPS_note": "未直接加總各季 EPS，避免配股或分割造成股數基準不一致。",
        "TTM_net_income": None,
        "TTM_net_income_date": None,
        "revenue": None,
        "revenue_date": None,
        "revenue_yoy": None,
        "gross_margin": None,
        "operating_margin": None,
        "net_margin": None,
        "financial_statement_date": None,
        "debt_ratio": None,
        "current_ratio": None,
        "balance_sheet_date": None,
        "operating_cash_flow": None,
        "cash_flow_date": None,
        "latest_cash_distribution": None,
        "cash_distribution_date": None,
        "nav": None,
        "premium_discount": None,
        "nav_date": None,
    }

    sources = []

    if asset_type == "stock":
        per_rows = finmind_request(
            "TaiwanStockPER", stock_id,
            (END_DATE - timedelta(days=60)).isoformat()
        )
        statement_rows = finmind_request(
            "TaiwanStockFinancialStatements", stock_id, start_date
        )
        balance_rows = finmind_request(
            "TaiwanStockBalanceSheet", stock_id, start_date
        )
        cash_rows = finmind_request(
            "TaiwanStockCashFlowsStatement", stock_id, start_date
        )
        revenue_rows = finmind_request(
            "TaiwanStockMonthRevenue", stock_id, start_date
        )
        sources.extend([
            "TaiwanStockPER", "TaiwanStockFinancialStatements",
            "TaiwanStockBalanceSheet", "TaiwanStockCashFlowsStatement",
            "TaiwanStockMonthRevenue",
        ])

        latest_per = latest_record(per_rows)
        output_data.update({
            "date": latest_per.get("date"),
            "PER": latest_per.get("PER"),
            "PBR": latest_per.get("PBR"),
            "dividend_yield": latest_per.get("dividend_yield"),
        })

        eps_rows = [
            row for row in statement_rows
            if row.get("type") == "EPS" and row.get("value") is not None
        ]
        latest_eps = latest_record(eps_rows)
        output_data["latest_quarter_EPS"] = (
            float(latest_eps["value"]) if latest_eps else None
        )
        output_data["EPS_date"] = latest_eps.get("date") if latest_eps else None

        quarter_dates = sorted({
            row.get("date") for row in statement_rows if row.get("date")
        })
        last_four_dates = quarter_dates[-4:]
        net_income_by_quarter = []
        for quarter_date in last_four_dates:
            values = [
                float(row["value"]) for row in statement_rows
                if row.get("date") == quarter_date
                and row.get("type") == "IncomeAfterTaxes"
                and row.get("value") is not None
            ]
            if values:
                net_income_by_quarter.append(values[-1])
        if len(last_four_dates) == 4 and len(net_income_by_quarter) == 4:
            output_data["TTM_net_income"] = sum(net_income_by_quarter)
            output_data["TTM_net_income_date"] = last_four_dates[-1]

        latest_statement_date = max(
            (row.get("date", "") for row in statement_rows), default=""
        )
        latest_statement = [
            row for row in statement_rows
            if row.get("date") == latest_statement_date
        ]
        revenue = value_for(latest_statement, "Revenue")
        gross_profit = value_for(latest_statement, "GrossProfit")
        operating_income = value_for(
            latest_statement, "OperatingIncome", "OperatingProfit"
        )
        net_income = value_for(latest_statement, "IncomeAfterTaxes")
        output_data.update({
            "gross_margin": safe_ratio(gross_profit, revenue, 100),
            "operating_margin": safe_ratio(operating_income, revenue, 100),
            "net_margin": safe_ratio(net_income, revenue, 100),
            "financial_statement_date": latest_statement_date or None,
        })

        latest_revenue = latest_record(revenue_rows)
        revenue_value = latest_revenue.get("revenue")
        revenue_yoy = None
        if latest_revenue and revenue_value is not None:
            try:
                this_year = int(latest_revenue["revenue_year"])
                this_month = int(latest_revenue["revenue_month"])
                prior = [
                    row for row in revenue_rows
                    if int(row.get("revenue_year", -1)) == this_year - 1
                    and int(row.get("revenue_month", -1)) == this_month
                    and row.get("revenue") is not None
                ]
                if prior and float(prior[-1]["revenue"]) != 0:
                    revenue_yoy = (
                        (float(revenue_value) - float(prior[-1]["revenue"]))
                        / float(prior[-1]["revenue"]) * 100
                    )
            except (TypeError, ValueError, KeyError):
                pass
        output_data.update({
            "revenue": revenue_value,
            "revenue_date": latest_revenue.get("date"),
            "revenue_yoy": revenue_yoy,
        })

        balance_date = max(
            (row.get("date", "") for row in balance_rows), default=""
        )
        latest_balance = [
            row for row in balance_rows if row.get("date") == balance_date
        ]
        total_assets = value_for(latest_balance, "TotalAssets")
        total_liabilities = value_for(latest_balance, "TotalLiabilities")
        current_assets = value_for(latest_balance, "CurrentAssets")
        current_liabilities = value_for(latest_balance, "CurrentLiabilities")
        output_data.update({
            "debt_ratio": safe_ratio(total_liabilities, total_assets, 100),
            "current_ratio": safe_ratio(current_assets, current_liabilities),
            "balance_sheet_date": balance_date or None,
        })

        cash_date = max(
            (row.get("date", "") for row in cash_rows), default=""
        )
        latest_cash = [
            row for row in cash_rows if row.get("date") == cash_date
        ]
        output_data.update({
            "operating_cash_flow": value_for(
                latest_cash, "CashFlowsFromOperatingActivities"
            ),
            "cash_flow_date": cash_date or None,
        })

    else:
        # ETF 不使用個股 PER、PBR、EPS 或公司財報比率。
        # 配息資料若來源有提供，僅顯示最近一次公告的每單位現金配息。
        try:
            dividend_rows = finmind_request(
                "TaiwanStockDividend", stock_id, start_date
            )
            latest_dividend = latest_record(dividend_rows)
            output_data.update({
                "latest_cash_distribution": latest_dividend.get(
                    "CashEarningsDistribution"
                ),
                "cash_distribution_date": latest_dividend.get("date"),
            })
            sources.append("TaiwanStockDividend")
        except Exception as exc:
            print(f"{stock_id} ETF 配息資料暫不可用：{exc}")

    has_data = asset_type == "etf" or any(
        value is not None
        for value in output_data.values()
    )
    output = {
        "stock_id": stock_id,
        "stock_name": stock_name,
        "asset_type": asset_type,
        "source": "FinMind " + " / ".join(sources) if sources else "FinMind",
        "status": "success" if has_data else "no_data",
        "message": None if has_data else "目前沒有可用資料。",
        "data": output_data,
        "notes": [
            "TTM EPS 未直接加總各季 EPS，避免配股或分割造成股數基準不一致。",
            "ETF 淨值與折溢價尚未自動串接；請以交易所或投信公告為準。",
        ] if asset_type == "etf" else [
            "各項財務指標採用最近可取得的已公告財報，並非即時資料。",
            "TTM EPS 不直接加總各季 EPS；本網站改顯示近四季本期淨利合計。",
        ],
    }

    output_dir = Path("data/fundamentals")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{stock_id}.json"
    output_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"{stock_id}（{stock_name}）基本面：{output['status']}，"
        f"類型：{asset_type}，資料日期：{output_data.get('date') or output_data.get('financial_statement_date')}"
    )


if __name__ == "__main__":
    catalog = get_stock_catalog()
    for stock_id in STOCK_IDS:
        fetch_stock_price(stock_id)
        fetch_stock_fundamental(stock_id, catalog)
