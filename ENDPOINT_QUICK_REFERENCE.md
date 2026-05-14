# API Endpoints Quick Reference

## Dashboard Integration Guide

This document shows which endpoint feeds which section of your dashboard.

---

## 1. VEBA Statistics Endpoint

**Endpoint:** `GET /veba/statistics`

**Frontend Variable:** `veba`

**Used In:** VEBA Governance Card

### Response Structure
```json
{
  "status": "success",
  "message": "VEBA statistics retrieved",
  "data": {
    "bookings_today": 184,
    "leakage_attempts": 17,
    "settlement_p95": "18m",
    "settlement_p95_minutes": 18.0
  }
}
```

### Frontend Code
```jsx
// Fetch VEBA statistics
const response = await fetch('/veba/statistics');
const json = await response.json();
const veba = json.data; // ⚠️ Note: Extract .data property

// VEBA Card Component
<Card title="VEBA Governance • Leakage Prevention" subtitle={vebaLoading ? "Loading…" : "Listings + tendering"}>
  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
    <MiniStat label="Bookings today"   value={vebaLoading || !veba || !veba.bookings_today ? "—" : veba.bookings_today.toLocaleString()} />
    <MiniStat label="Leakage attempts" value={vebaLoading || !veba || !veba.leakage_attempts ? "—" : veba.leakage_attempts.toLocaleString()} />
    <MiniStat label="Settlement p95"   value={vebaLoading || !veba || !veba.settlement_p95 ? "—" : veba.settlement_p95} />
  </div>
</Card>
```

**⚠️ Important:** Response is wrapped in `{status, message, data}` structure. Access via `response.data.bookings_today`

---

## 2. API Performance Endpoint

**Endpoint:** `GET /metrics/api/performance`

**Frontend Variable:** `perf`

**Used In:** KPI Grid (Uptime, Latency, Kafka Lag, Request Rate)

### Response Structure
```json
{
  "ok": true,
  "timestamp": "2026-03-05T07:20:11.262103",
  "metrics_window_seconds": 300,
  "api_latency": {
    "p50_ms": 45.23,
    "p95_ms": 320.15,
    "p99_ms": 1250.89,
    "avg_ms": 125.45,
    "min_ms": 5.12,
    "max_ms": 5000.23,
    "sample_count": 10000
  },
  "error_rates": {
    "success_rate_percent": 99.3,
    "error_4xx_rate_percent": 0.5,
    "error_5xx_rate_percent": 0.2,
    "error_4xx_count": 50,
    "error_5xx_count": 20,
    "success_count": 9930,
    "total_requests": 10000
  },
  "request_rates": {
    "requests_per_second": 33.33,
    "requests_per_minute": 2000.0,
    "total_requests_lifetime": 1000000
  },
  "kafka": {
    "consumer_lag": {
      "total_lag": 482,
      "by_topic": {
        "device-telemetry": 320,
        "payment-events": 100
      },
      "consumer_group": "navas-iot-consumers"
    },
    "last_update": "2026-03-05T07:19:44.557570",
    "error": null
  },
  "uptime": {
    "seconds": 953.16,
    "days": 0.01,
    "percentage_30d": 99.5,
    "start_time": "2026-03-05T07:04:13.852127"
  },
  "top_endpoints": {
    "GET /data/stream": 3500,
    "POST /devices/register": 2200
  }
}
```

### Frontend Code
```jsx
// Fetch performance metrics
const perf = await fetch('/metrics/api/performance').then(r => r.json());

// KPI Grid Component
<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
  <Kpi
    title="Uptime (30d)"
    value={perfLoading || !perf || !perf.uptime?.percentage_30d ? "—" : `${perf.uptime.percentage_30d}%`}
    sub={perfLoading || !perf || !perf.api_latency?.p95_ms || !perf.error_rates?.error_5xx_rate_percent ? "Loading…" : `p95 ${perf.api_latency.p95_ms.toFixed(0)}ms • 5xx ${perf.error_rates.error_5xx_rate_percent}%`}
    sev={!perf || !perf.uptime?.percentage_30d ? "green" : perf.uptime.percentage_30d >= 99.5 ? "green" : perf.uptime.percentage_30d >= 99 ? "warning" : "alarm"}
  />
  <Kpi
    title="API Latency p95"
    value={perfLoading || !perf || !perf.api_latency?.p95_ms ? "—" : `${perf.api_latency.p95_ms.toFixed(0)}ms`}
    sub={perfLoading || !perf || !perf.api_latency?.p50_ms || !perf.api_latency?.p99_ms ? "Loading…" : `p50 ${perf.api_latency.p50_ms.toFixed(0)}ms • p99 ${perf.api_latency.p99_ms.toFixed(0)}ms`}
    sev={!perf || !perf.api_latency?.p95_ms ? "green" : perf.api_latency.p95_ms < 500 ? "green" : perf.api_latency.p95_ms < 1000 ? "warning" : "alarm"}
  />
  <Kpi
    title="Kafka Lag"
    value={perfLoading || !perf || !perf.kafka?.consumer_lag?.total_lag ? "—" : perf.kafka.consumer_lag.total_lag.toLocaleString()}
    sub={perfLoading || !perf || !perf.kafka?.consumer_lag ? "Loading…" : `group: ${perf.kafka.consumer_lag.consumer_group || '—'} • ${Object.keys(perf.kafka.consumer_lag.by_topic || {}).length} topics`}
    sev={!perf || !perf.kafka?.consumer_lag?.total_lag ? "green" : perf.kafka.consumer_lag.total_lag < 500 ? "green" : perf.kafka.consumer_lag.total_lag < 1000 ? "warning" : "alarm"}
  />
  <Kpi
    title="Request Rate"
    value={perfLoading || !perf || !perf.request_rates?.requests_per_second ? "—" : `${perf.request_rates.requests_per_second.toFixed(1)} req/s`}
    sub={perfLoading || !perf || !perf.error_rates?.total_requests || !perf.error_rates?.success_rate_percent ? "Loading…" : `${perf.error_rates.total_requests.toLocaleString()} total • ${perf.error_rates.success_rate_percent}% success`}
    sev={!perf || !perf.error_rates?.error_5xx_rate_percent ? "green" : perf.error_rates.error_5xx_rate_percent < 1 ? "green" : perf.error_rates.error_5xx_rate_percent < 3 ? "warning" : "alarm"}
  />
</div>
```

**✅ Note:** Response data is at root level. Access via `perf.uptime.percentage_30d` directly.

---

## Key Differences

| Aspect | `/veba/statistics` | `/metrics/api/performance` |
|--------|-------------------|---------------------------|
| **Response Format** | Wrapped in `{status, message, data}` | Direct JSON object with `ok` flag |
| **Data Access** | `response.data.bookings_today` | `response.uptime.percentage_30d` |
| **Purpose** | VEBA-specific business metrics | API/system performance metrics |
| **Refresh Rate** | 30 seconds recommended | 10 seconds recommended |
| **Database** | PostgreSQL (`dll_veba_statistics`) | In-memory metrics collector |

---

## Testing Commands

```bash
# Test VEBA endpoint
curl http://127.0.0.1:5000/veba/statistics | python -m json.tool

# Test Performance endpoint
curl http://127.0.0.1:5000/metrics/api/performance | python -m json.tool
```

---

## Documentation Files

- **VEBA Statistics:** `veba-statistics-api-docs.json`
- **API Performance:** `metrics-api-performance-docs.json`
- **Full Metrics Docs:** `metrics-api-docs.json`
