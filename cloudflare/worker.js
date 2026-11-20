const FINMIND_URL = "https://api.finmindtrade.com/api/v4/data";
const ALLOWED_ORIGIN = "https://mengqi1998.github.io";

function corsHeaders(origin) {
  const allowed = origin === ALLOWED_ORIGIN ? origin : ALLOWED_ORIGIN;
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin"
  };
}

function jsonResponse(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders(origin),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=900"
    }
  });
}

async function finmindRequest(env, dataset, stockId, startDate) {
  const params = new URLSearchParams({ dataset, data_id: stockId, start_date: startDate });
  const response = await fetch(`${FINMIND_URL}?${params.toString()}`, {
    headers: env.FINMIND_TOKEN
      ? { Authorization: `Bearer ${env.FINMIND_TOKEN}` }
      : {}
  });
  const result = await response.json();
  if (!response.ok || result.status !== 200) {
    throw new Error(`FinMind ${dataset} 查詢失敗：${JSON.stringify(result)}`);
  }
  return Array.isArray(result.data) ? result.data : [];
}

function dateDaysAgo(days) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function calculateFiveLines(records, stockId) {
  const byDate = new Map();
  for (const row of records) {
    const date = String(row.date || "");
    let close = Number(row.close);
    if (!date || !Number.isFinite(close) || close <= 0) continue;

    // 0050 於 2025-06-18 進行 1 拆 4；將拆分前價格換算為拆分後單位。
    if (stockId === "0050" && date < "2025-06-18") close /= 4;
    byDate.set(date, { date, close });
  }

  const prices = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  const windowSize = 500;
  const results = [];

  for (let end = windowSize - 1; end < prices.length; end++) {
    const start = end - windowSize + 1;
    const window = prices.slice(start, end + 1);
    const y = window.map(item => item.close);
    const xMean = (windowSize - 1) / 2;
    const yMean = y.reduce((sum, value) => sum + value, 0) / windowSize;

    let numerator = 0;
    let denominator = 0;
    for (let i = 0; i < windowSize; i++) {
      numerator += (i - xMean) * (y[i] - yMean);
      denominator += (i - xMean) ** 2;
    }

    const slope = numerator / denominator;
    const intercept = yMean - slope * xMean;
    let squaredError = 0;
    for (let i = 0; i < windowSize; i++) {
      const residual = y[i] - (slope * i + intercept);
      squaredError += residual * residual;
    }
    const sigma = Math.sqrt(squaredError / windowSize);
    const trend = slope * (windowSize - 1) + intercept;
    const close = prices[end].close;

    results.push({
      date: prices[end].date,
      close,
      trend,
      upper_1: trend + sigma,
      lower_1: trend - sigma,
      upper_2: trend + 2 * sigma,
      lower_2: trend - 2 * sigma,
      buy_signal: false,
      sell_signal: false,
      signal: "none",
      slope,
      intercept,
      sigma
    });
  }

  for (let i = 1; i < results.length; i++) {
    const previous = results[i - 1];
    const current = results[i];
    if (previous.close < previous.lower_2 && current.close >= current.lower_2) {
      current.buy_signal = true;
      current.signal = "buy";
    } else if (previous.close > previous.upper_2 && current.close <= current.upper_2) {
      current.sell_signal = true;
      current.signal = "sell";
    }
  }

  const output = results.slice(-500);
  const latest = output[output.length - 1] || null;
  const success = output.length === 500;

  return {
    stock_id: stockId,
    window: windowSize,
    actual_days: output.length,
    raw_days: prices.length,
    status: success ? "success" : "insufficient_data",
    message: success ? null : `至少需要 ${windowSize + 499} 個交易日，目前取得 ${prices.length} 筆，可計算 ${output.length} 天。`,
    calculation_method: "rolling_linear_regression",
    price_adjustment: stockId === "0050"
      ? "0050 split-adjusted (pre-2025-06-18 prices divided by 4); dividends not adjusted"
      : "No corporate-action adjustment; dividends not adjusted",
    sigma: latest ? Number(latest.sigma.toFixed(4)) : null,
    slope: latest ? Number(latest.slope.toFixed(8)) : null,
    intercept: latest ? Number(latest.intercept.toFixed(8)) : null,
    latest_signal: latest ? latest.signal : "none",
    data: success ? output.map(row => ({
      ...row,
      close: Number(row.close.toFixed(4)),
      trend: Number(row.trend.toFixed(4)),
      upper_1: Number(row.upper_1.toFixed(4)),
      lower_1: Number(row.lower_1.toFixed(4)),
      upper_2: Number(row.upper_2.toFixed(4)),
      lower_2: Number(row.lower_2.toFixed(4)),
      slope: Number(row.slope.toFixed(8)),
      intercept: Number(row.intercept.toFixed(8)),
      sigma: Number(row.sigma.toFixed(4))
    })) : []
  };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return jsonResponse({ ok: true, service: "lohas-stock-api" }, 200, origin);
    }

    const match = url.pathname.match(/^\/api\/stock\/([0-9A-Za-z]{4,6})$/);
    if (request.method !== "GET" || !match) {
      return jsonResponse({ status: "error", message: "請求路徑錯誤。使用 /api/stock/股票代號" }, 404, origin);
    }

    const stockId = match[1].toUpperCase();
    if (!env.FINMIND_TOKEN) {
      return jsonResponse({ status: "error", message: "Worker 尚未設定 FINMIND_TOKEN Secret。" }, 500, origin);
    }

    try {
      const records = await finmindRequest(env, "TaiwanStockPrice", stockId, dateDaysAgo(1800));
      if (!records.length) {
        return jsonResponse({ status: "error", message: `查不到 ${stockId} 的股價資料，請確認代號是否有效。` }, 404, origin);
      }
      const data = calculateFiveLines(records, stockId);
      return jsonResponse(data, data.status === "success" ? 200 : 422, origin);
    } catch (error) {
      return jsonResponse({ status: "error", message: error.message || "查詢股票資料時發生錯誤。" }, 502, origin);
    }
  }
};
