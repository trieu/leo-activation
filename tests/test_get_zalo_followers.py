import csv
import time # Import time for rate-limiting
import logging
import os
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv() 

from main_configs import MarketingConfigs
from agentic_tools.channels.zalo import ZaloOAChannel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def get_arango_db():
    host = os.getenv("ARANGO_HOST", "http://localhost:8529")
    db_name = os.getenv("ARANGO_DB", "your_actual_db_name")
    username = os.getenv("ARANGO_USER", "root")
    password = os.getenv("ARANGO_PASSWORD", "")

    client = ArangoClient(hosts=host)
    return client.db(db_name, username=username, password=password)

def export_followers_to_csv(limit: int = 100, filename: str = "zalo_followers.csv"):
    print(f"🚀 Initializing Zalo OA connection to fetch up to {limit} followers...")
    
    db_connection = get_arango_db()
    channel = ZaloOAChannel(db_client=db_connection)
    
    # 1. Fetch the raw IDs
    basic_followers = channel.get_oa_followers(limit=limit)
    
    if not basic_followers:
        print("⚠️ No followers found.")
        return

    print(f"✅ Found {len(basic_followers)} IDs. Now fetching detailed profiles...")
    
    detailed_followers = []
    
    # 2. Fetch details for each ID
    for index, user in enumerate(basic_followers):
        user_id = user.get("user_id")
        if not user_id:
            continue
            
        print(f"   ⏳ Fetching details for {user_id} ({index + 1}/{len(basic_followers)})...")
        
        # Call the new detail method
        profile = channel.get_user_detail(user_id)
        
        # Merge the basic user_id with the new profile data
        detailed_followers.append({
            "user_id": user_id,
            "display_name": profile.get("display_name", "Unknown"),
            "avatar": profile.get("avatar", "")
        })
        
        # Crucial: Sleep for 0.2 seconds to respect Zalo's rate limits
        time.sleep(0.2) 

    # 3. Write to CSV
    headers = ["user_id", "display_name", "avatar"]
    
    try:
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(detailed_followers) # We can write all rows at once now
                
        print(f"🎉 Success! Saved {len(detailed_followers)} detailed profiles to '{filename}'.")
        
    except Exception as e:
        print(f"❌ Failed to write the CSV file. Error: {e}")

if __name__ == "__main__":
    export_followers_to_csv(limit=10, filename="oa_followers_export.csv") # Start with limit=10 to test!