from fastapi import FastAPI
from pymongo import MongoClient

app = FastAPI()

client = MongoClient("mongodb://localhost:27018/")
db = client["amf_logs"]


@app.get("/locations")
def get_locations():
    data = list(db.location_info.find({}, {"_id": 0}))
    return data

