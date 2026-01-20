import os
from pymongo import MongoClient

def get_db():
    uri = os.getenv("MONGO_URI", "").strip()
    dbn = os.getenv("MONGO_DB", "fabrix").strip()
    if not uri:
        raise RuntimeError("MONGO_URI missing. Set it in .env")
    client = MongoClient(uri)
    return client[dbn]
