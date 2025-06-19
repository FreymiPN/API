from flask import Flask, jsonify, request
from bson import ObjectId
from dotenv import load_dotenv
import os
import certifi
from pymongo import MongoClient

# .env nur lokal laden. Render verwendet die Umgebungsvariablen direkt.
load_dotenv()

# Zugriff auf MONGO_URI aus Umgebungsvariable
MONGO_URI = os.environ.get("MONGO_URI")

# Flask App initialisieren
app = Flask(__name__)


# MongoDB-Verbindung aufbauen
try:
    # MongoDB URI wird sicher aus der Umgebungsvariable MONGO_URI geladen.
    mongo_uri = os.getenv("MONGO_URI")

    # Überprüfung, ob die Umgebungsvariable MONGO_URI gesetzt ist.
    if not mongo_uri:
        raise ValueError(
            "MONGO_URI Umgebungsvariable ist nicht gesetzt. Bitte in den Render Environment Variables prüfen."
        )

    # Ausgabe der verwendeten URI (ohne sensible Teile) zur Debugging-Hilfe im Log
    print(
        f"Verbindungs-URI (aus Umgebungsvariable geladen): {mongo_uri.split('@')[0]}@...{mongo_uri.split('/')[-1]}"
    )

    # Aufbau der MongoDB-Verbindung
    client = MongoClient(mongo_uri)

    # Testen der Verbindung durch einen Ping-Befehl an die Datenbank
    client.admin.command("ping")
    print("Erfolgreich mit MongoDB Atlas verbunden!")

    # Auswahl der Datenbank und der Collections
    db = client["SmarthomeBox"]
    test_collection = db["test"]
    print("Datenbank 'SmarthomeBox' und Collections ausgewählt.")

except Exception as e:
    # Fehlerbehandlung für Verbindungsprobleme.
    print(f"FEHLER: Probleme beim Aufbau der MongoDB-Verbindung: {e}")
    # Setzt Collections auf None, um Folgefehler bei API-Aufrufen zu verhindern
    db = None
    client = None
    test_collection = None


# API-Endpunkt zum Lesen der Daten
@app.route("/read", methods=["GET"])
def read():
    if test_collection is None:
        return jsonify({"error": "Keine Verbindung zur Datenbank"}), 500
    try:
        documents = test_collection.find()
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
