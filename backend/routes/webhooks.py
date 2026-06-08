from pymongo import MongoClient
import os

# Connect to your MongoDB
client = MongoClient(os.getenv('MONGO_URL'))
db = client[os.getenv('DB_NAME')]
users = db.users

# Perform the update
result = users.update_many(
    {"state": {"$exists": False}}, 
    {"$set": {"state": "UNKNOWN"}}
)

print(f"Migration complete: {result.modified_count} users updated.")
