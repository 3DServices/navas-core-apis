#!/usr/bin/env python3
"""
Test script for gateway endpoints
"""

import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_get_all_gateways():
    """Test GET /gateways/mobile-money - Get all current gateway statuses"""
    print("\n" + "="*70)
    print("TEST 1: GET /gateways/mobile-money")
    print("="*70)
    
    try:
        response = requests.get(f"{BASE_URL}/gateways/mobile-money")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Success! Found {len(data.get('gateways', []))} gateways")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Error: {response.text}")
    except Exception as e:
        print(f"❌ Request failed: {e}")

def test_get_gateway_history():
    """Test GET /gateways/mobile-money/<telecom_name> - Get gateway history"""
    print("\n" + "="*70)
    print("TEST 2: GET /gateways/mobile-money/M-Pesa KE")
    print("="*70)
    
    try:
        # URL encode the space in "M-Pesa KE"
        response = requests.get(f"{BASE_URL}/gateways/mobile-money/M-Pesa KE")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            history = data.get('history', [])
            print(f"\n✅ Success! Found {len(history)} history records for M-Pesa KE")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Error: {response.text}")
    except Exception as e:
        print(f"❌ Request failed: {e}")

def test_update_gateway_status():
    """Test POST /gateways/mobile-money/update - Update gateway status"""
    print("\n" + "="*70)
    print("TEST 3: POST /gateways/mobile-money/update")
    print("="*70)
    
    payload = {
        "telecom": "M-Pesa KE",
        "api_status": "DEGRADED",
        "message": "success 87.3% • timeout 8.1% • p95 21.4s"
    }
    
    print(f"\nPayload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/gateways/mobile-money/update",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Gateway status updated")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Error: {response.text}")
    except Exception as e:
        print(f"❌ Request failed: {e}")

def test_get_all_after_update():
    """Test GET /gateways/mobile-money again to verify the update"""
    print("\n" + "="*70)
    print("TEST 4: GET /gateways/mobile-money (Verify Update)")
    print("="*70)
    
    try:
        response = requests.get(f"{BASE_URL}/gateways/mobile-money")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            gateways = data.get('gateways', [])
            print(f"\n✅ Current gateway statuses:")
            for gw in gateways:
                status_icon = "🟢" if gw['status'] == "OK" else "🟡" if gw['status'] == "DEGRADED" else "🔴"
                print(f"  {status_icon} {gw['name']}: {gw['status']} | {gw['meta']}")
        else:
            print(f"❌ Error: {response.text}")
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    print("\n🧪 TESTING GATEWAY ENDPOINTS")
    print("="*70)
    
    # Run all tests
    test_get_all_gateways()
    test_get_gateway_history()
    test_update_gateway_status()
    test_get_all_after_update()
    
    print("\n" + "="*70)
    print("✅ All tests completed!")
    print("="*70 + "\n")
