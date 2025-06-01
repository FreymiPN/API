from flask import Flask, jsonify, request
from bson import ObjectId
from dotenv import load_dotenv
import os
import certifi
import pymongo

load_dotenv()  # lädt Variablen aus der .env-Datei

MONGO_URI = os.environ.get("MONGO_URI")


# creating a Flask application
app = Flask(__name__)

# MongoDB-connection aufbauen
try:
    client = pymongo.MongoClient(MONGO_URI + "?tlsCAFile=" + certifi.where())
    print("Erfolgreich mit MongoDB verbunden!")
except Exception as e:
    print(f"Fehler: {e}")

# connection to database and collection
db = client["SmarthomeBox"]
collection = db["test"]


@app.route("/read", methods=["GET"])
def read():
    documents = collection.find()
    result = []
    for doc in documents:
        doc["_id"] = str(doc["_id"])  # ObjectId in String umwandeln
        result.append(doc)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
