import requests
import json
import time

print("="*70)
print("TESTING METRICS MIDDLEWARE")
print("="*70)

# Step 1: Check initial metrics
print("\n1. Checking initial /metrics/server state...")
response = requests.get('http://127.0.0.1:5000/metrics/server')
initial_data = response.json()
print(f"Initial total_requests_lifetime: {initial_data['request_rates']['total_requests_lifetime']}")
print(f"Initial sample_count: {initial_data['api_latency']['sample_count']}")

# Step 2: Make requests to other endpoints
print("\n2. Making 10 requests to /metrics/health...")
for i in range(10):
    requests.get('http://127.0.0.1:5000/metrics/health')
    time.sleep(0.1)

# Step 3: Check metrics again
print("\n3. Checking /metrics/server after traffic...")
time.sleep(1)
response = requests.get('http://127.0.0.1:5000/metrics/server')
after_data = response.json()

print(f"\nAfter total_requests_lifetime: {after_data['request_rates']['total_requests_lifetime']}")
print(f"After sample_count: {after_data['api_latency']['sample_count']}")
print(f"After requests_per_second: {after_data['request_rates']['requests_per_second']}")

if after_data['api_latency']['sample_count'] > 0:
    print(f"\np50: {after_data['api_latency']['p50_ms']}ms")
    print(f"p95: {after_data['api_latency']['p95_ms']}ms")
    print(f"p99: {after_data['api_latency']['p99_ms']}ms")
    print(f"avg: {after_data['api_latency']['avg_ms']}ms")
    print(f"\n✅ MIDDLEWARE IS WORKING!")
else:
    print(f"\n❌ MIDDLEWARE NOT CAPTURING DATA")

print("\nTop endpoints:")
print(json.dumps(after_data['top_endpoints'], indent=2))

print("\n" + "="*70)
