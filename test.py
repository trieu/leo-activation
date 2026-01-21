from arango import ArangoClient
import os

# Connect to the default system database to check list
client = ArangoClient(hosts=os.getenv("ARANGO_HOST", "http://localhost:8529"))
sys_db = client.db('_system', username=os.getenv("ARANGO_USER", "root"), password=os.getenv("ARANGO_PASSWORD", ""))

print("Available Databases:", sys_db.databases())