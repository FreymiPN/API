from flask import Flask, jsonify, request
from bson import ObjectId
from dotenv import load_dotenv
import os
import certifi
import pymongo

# .env nur lokal laden. Render verwendet die Umgebungsvariablen direkt.
load_dotenv()

# Zugriff auf MONGO_URI aus Umgebungsvariable
MONGO_URI = os.environ.get("MONGO_URI")

# Flask App initialisieren
app = Flask(__name__)

# MongoDB Client vorbereiten
client = None
db = None
collection = None

# MongoDB-Verbindung aufbauen
try:
    if MONGO_URI is None:
        raise ValueError(
            "MONGO_URI environment variable is not set. Please set it in Render Dashboard or .env file."
        )

    # Wenn URI bereits Parameter enthält, hänge den neuen per "&" an, sonst mit "?"
    tls_param = "tlsCAFile=" + certifi.where()
    if "?" in MONGO_URI:
        full_uri = MONGO_URI + "&" + tls_param
    else:
        full_uri = MONGO_URI + "?" + tls_param

    client = pymongo.MongoClient(full_uri)
    client.admin.command("ping")
    print("Erfolgreich mit MongoDB verbunden!")

    db = client["SmarthomeBox"]
    collection = db["test"]
    print("Datenbank 'SmarthomeBox' und Collection 'test' ausgewählt.")

except Exception as e:
    print(f"Fehler bei der MongoDB-Verbindung: {e}")


# API-Endpunkt zum Lesen der Daten
@app.route("/read", methods=["GET"])
def read():
    if collection is None:
        return jsonify({"error": "Keine Verbindung zur Datenbank"}), 500
    try:
        documents = collection.find()
        result = []
        for doc in documents:
            doc["_id"] = str(doc["_id"])  # ObjectId in String umwandeln
            result.append(doc)
        return jsonify(result)
    except Exception as e:
        print(f"Fehler beim Lesen: {e}")
        return jsonify({"error": "Fehler beim Lesen", "details": str(e)}), 500


# Nur lokal starten. Render übernimmt das mit Gunicorn.
if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))
