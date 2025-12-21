
import requests

from typing import Dict, Any


def get_current_weather(location: str, unit: str = "celsius") -> Dict[str, Any]:
    """
    Get real-time weather using Open-Meteo API.

    Args:
        location: The city or location name (e.g., 'Saigon').
        unit: Temperature unit, either 'celsius' or 'fahrenheit'.
    """
    locations = {
        "saigon": {"lat": 10.8231, "lon": 106.6297},
        "ho chi minh city": {"lat": 10.8231, "lon": 106.6297},
        "hanoi": {"lat": 21.0285, "lon": 105.8542},
        "tokyo": {"lat": 35.6895, "lon": 139.6917},
    }
    loc_key = location.lower().split(",")[0].strip()
    coords = locations.get(loc_key, locations["saigon"])
    url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true"

    try:
        response = requests.get(url, timeout=10).json()
        current = response.get("current_weather", {})
        return {
            "location": location,
            "temperature": f"{current.get('temperature', 'N/A')}°{unit[0].upper()}",
            "condition_code": current.get("weathercode"),
            "source": "Open-Meteo",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
