from flask import Flask, jsonify, request
from bson import ObjectId
from dotenv import load_dotenv
import os
import certifi
import pymongo

# Lade .env nur lokal. Render nutzt Umgebungsvariablen direkt aus seinem Dashboard.
load_dotenv()

# Zugriff auf MONGO_URI aus Umgebungsvariable
MONGO_URI = os.environ.get("MONGO_URI")

# Flask App initialisieren
app = Flask(__name__)

# Initialisiere client, db, collection außerhalb der try-Blöcke,
# um sicherzustellen, dass sie immer definiert sind (ggf. als None)
client = None
db = None
collection = None

# MongoDB-connection aufbauen
try:
    # Wichtig: Prüfe, ob MONGO_URI überhaupt gesetzt ist
    if MONGO_URI is None:
        raise ValueError(
            "MONGO_URI environment variable is not set. Please set it in Render Dashboard or .env file."
        )

    client = pymongo.MongoClient(MONGO_URI + "?tlsCAFile=" + certifi.where())
    # Optional: Ein kurzer Ping, um die Verbindung zu verifizieren
    client.admin.command("ping")
    print("Erfolgreich mit MongoDB verbunden!")

    # Verbindung zu Datenbank und Collection erst HIER aufbauen,
    # nachdem 'client' definitiv erfolgreich initialisiert wurde
    db = client["SmarthomeBox"]
    collection = db["test"]
    print("Datenbank 'SmarthomeBox' und Collection 'test' ausgewählt.")

except Exception as e:
    # Diese Fehlermeldung wird in den Render-Logs sichtbar sein
    print(
        f"FEHLER: Probleme beim Aufbau der MongoDB-Verbindung oder Datenbankauswahl: {e}"
    )
    # Hier könnten wir auch einen leeren Client oder eine "Mock"-Collection setzen,
    # um die App zum Laufen zu bringen, aber keine DB-Operationen zuzulassen.
    # Für eine kritische App würde man hier ggf. sys.exit(1) aufrufen.


@app.route("/read", methods=["GET"])
def read():
    # Prüfe hier, ob die Collection verfügbar ist, bevor du darauf zugreifst
    if collection is None:
        return (
            jsonify(
                {
                    "error": "Datenbankverbindung nicht verfügbar. Bitte kontaktieren Sie den Support."
                }
            ),
            500,
        )
    try:
        documents = collection.find()
        result = []
        for doc in documents:
            doc["_id"] = str(doc["_id"])  # ObjectId in String umwandeln
            result.append(doc)
        return jsonify(result)
    except Exception as e:
        # Fange Fehler ab, die während der Datenbankabfrage auftreten könnten
        print(f"Fehler beim Lesen der Dokumente: {e}")
        return (
            jsonify({"error": "Fehler beim Abrufen der Dokumente", "details": str(e)}),
            500,
        )


# Start nur lokal sinnvoll – Render nutzt Gunicorn.
# Der 'if __name__ == "__main__":' Block wird auf Render nicht ausgeführt.
if __name__ == "__main__":
    # debug=True nicht für Produktion verwenden.
    # Render weist dynamisch einen Port zu (oft 10000). Lokal kannst du 5000 verwenden.
    app.run(debug=True, port=os.getenv("PORT", 5000))
