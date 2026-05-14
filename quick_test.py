import requests
import json

print("Testing Metrics Endpoints\n" + "="*60)

# Test 1: Health Check
print("\n1. Testing /metrics/health")
try:
    response = requests.get('http://127.0.0.1:5000/metrics/health', timeout=5)
    if response.status_code == 200:
        print(f"✓ SUCCESS (Status: {response.status_code})")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"✗ FAILED (Status: {response.status_code})")
        print(response.text)
except Exception as e:
    print(f"✗ ERROR: {e}")

# Test 2: Server Metrics
print("\n" + "="*60)
print("\n2. Testing /metrics/server")
try:
    response = requests.get('http://127.0.0.1:5000/metrics/server', timeout=10)
    if response.status_code == 200:
        data = response.json()
        print(f"✓ SUCCESS (Status: {response.status_code})")
        print("\nKey Metrics:")
        print(f"  - Uptime: {data.get('uptime', {}).get('percentage_30d')}%")
        print(f"  - CPU: {data.get('system', {}).get('cpu_percent')}%")
        print(f"  - Memory: {data.get('system', {}).get('memory_percent')}%")
        print(f"  - API p95: {data.get('api_latency', {}).get('p95_ms')}ms")
        print(f"  - 5xx Rate: {data.get('error_rates', {}).get('error_5xx_rate_percent')}%")
        print(f"  - Requests/sec: {data.get('request_rates', {}).get('requests_per_second')}")
        print(f"\n  Full response:")
        print(json.dumps(data, indent=2)[:1000] + "...(truncated)")
    else:
        print(f"✗ FAILED (Status: {response.status_code})")
        print(response.text)
except Exception as e:
    print(f"✗ ERROR: {e}")

print("\n" + "="*60)
print("\nTest Complete!")
