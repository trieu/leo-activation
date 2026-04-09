import requests
import json

# Configuration
BASE_URL = "http://0.0.0.0:8000"  # Match your MAIN_APP_PORT
SIMULATE_URL = f"{BASE_URL}/api/v1/simulate"

def test_simulation_flow():
    # 1. Define the Human Profile (LEO CDP Format)
    # We include custom HumanSoulMeta to test the dynamic refactoring
    payload = {
        "name": "trieu",
        "faith": 0.6,
        "sin_level": 0.5,
        "reason": 0.5,
        "emotion": 0.5,
        "discipline": 0.4,
        "meta": {
            #"events": ["SUCCESS", "GRACE", "REFLECTION"], # Custom event pool
            #"theology_models": ["PAUL", "AUGUSTINE", "AQUINAS"], # Custom theology models
            "hyperparameters": {
                "steps": 2000,
                "epsilon": 0.1
            },
            "colors": {
                "faith": "#0000FF", # Custom blue for faith
                "reward": "#FFD700"  # Gold for reward
            }
        }
    }

    print(f"🚀 Sending simulation request for: {payload['name']}...")
    
    # 2. Call the Simulation API
    try:
        response = requests.post(SIMULATE_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        
        print("✅ Simulation Complete!")
        print(f"📄 Report Filename: {result['report_filename']}")
        print(f"🔗 Report URL: {result['report_url']}")

        # 3. Test the HTML File Handler
        report_url = f"{BASE_URL}{result['report_url']}"
        print(f"\n📡 Fetching HTML report from {report_url}...")
        
        report_response = requests.get(report_url)
        if report_response.status_code == 200:
            print("✅ Successfully retrieved HTML content.")
            # Optional: Save locally to verify
            with open("test_output.html", "w", encoding="utf-8") as f:
                f.write(report_response.text)
            print("💾 Report saved locally as 'test_output.html'")
        else:
            print(f"❌ Failed to retrieve report: {report_response.status_code}")

    except requests.exceptions.ConnectionError:
        print("❌ Error: Is the API server running? Check your uvicorn status.")
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    test_simulation_flow()