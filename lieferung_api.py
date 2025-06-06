import random
import string

# certifi wird nicht mehr explizit importiert, da es für Render-Deployment nicht direkt benötigt wird.
from pymongo import MongoClient
from flask import Flask, request, jsonify
import os

# python-dotenv wird nicht importiert, da Umgebungsvariablen direkt von Render kommen.

app = Flask(__name__)

# Initialisierung der MongoDB-Client und Collection-Objekte
client = None
db = None
kunden_collection = None
lieferungen_collection = None
geodaten_collection = None

try:
    # MongoDB URI wird sicher aus der Umgebungsvariable MONGO_URI geladen.
    mongo_uri = os.getenv("MONGO_URI")

    # Überprüfung, ob die Umgebungsvariable MONGO_URI gesetzt ist.
    if not mongo_uri:
        raise ValueError(
            "MONGO_URI Umgebungsvariable ist nicht gesetzt. Bitte in den Render Environment Variables prüfen."
        )

    # Ausgabe der verwendeten URI (ohne sensible Teile) zur Debugging-Hilfe im Log.
    # Wichtig: Das Passwort wird hier nicht vollständig ausgegeben.
    print(
        f"Verbindungs-URI (aus Umgebungsvariable geladen): {mongo_uri.split('@')[0]}@...{mongo_uri.split('/')[-1]}"
    )

    # Aufbau der MongoDB-Verbindung. Für Render wird tlsCAFile nicht explizit benötigt,
    # da die Render-Umgebung die SSL-Zertifikate automatisch handhabt.
    client = MongoClient(mongo_uri)

    # Testen der Verbindung durch einen Ping-Befehl an die Datenbank.
    client.admin.command("ping")
    print("Erfolgreich mit MongoDB Atlas verbunden!")

    # Auswahl der Datenbank und der Collections.
    # Der Datenbankname "SmarthomeBox" sollte Teil der MONGO_URI sein.
    db = client["SmarthomeBox"]
    kunden_collection = db["kunden"]
    lieferungen_collection = db["lieferungen"]
    geodaten_collection = db["geodaten"]
    print("Datenbank 'SmarthomeBox' und Collections ausgewählt.")

except Exception as e:
    # Fehlerbehandlung für Verbindungsprobleme.
    print(f"FEHLER: Probleme beim Aufbau der MongoDB-Verbindung: {e}")
    # Setzt Collections auf None, um Folgefehler bei API-Aufrufen zu verhindern.
    db = None
    kunden_collection = None
    lieferungen_collection = None
    geodaten_collection = None


# Hilfsfunktion zur Generierung eines zufälligen Sicherheitsschlüssels.
def generate_security_key():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


# Hilfsfunktion zur Überprüfung des Datenbankverbindungsstatus vor API-Aufrufen.
def check_db_connection():
    if (
        kunden_collection is None
        or lieferungen_collection is None
        or geodaten_collection is None
    ):
        return (
            jsonify(
                {
                    "error": "Datenbankverbindung nicht verfügbar. Bitte kontaktieren Sie den Support."
                }
            ),
            500,
        )
    return None


# API-Endpunkt zum Erstellen eines neuen Kunden.
@app.route("/create_customer", methods=["POST"])
def create_customer():
    # Überprüft die DB-Verbindung.
    error_response = check_db_connection()
    if error_response:
        return error_response

    data = request.json
    try:
        if "name" not in data or "adresse" not in data or "email" not in data:
            return (
                jsonify({"error": "Name und Adresse des Kunden sind erforderlich"}),
                400,
            )
        customer_data = {
            "name": data["name"],
            "email": data["email"],
            "adresse": data["adresse"],
        }

        # Prüfen, ob Kunde bereits existiert.
        if kunden_collection.find_one({"name": data["name"]}):
            return jsonify({"error": "Kunde mit diesem Namen existiert bereits"}), 409

        # Kunden in die Datenbank einfügen.
        customer_id = kunden_collection.insert_one(customer_data).inserted_id
        return (
            jsonify(
                {
                    "message": "Kunde erfolgreich erstellt",
                    "customer_id": str(customer_id),
                }
            ),
            201,
        )
    except Exception as e:
        print(f"Fehler in create_customer: {e}")
        return (
            jsonify(
                {
                    "error": "Interner Serverfehler beim Erstellen des Kunden",
                    "details": str(e),
                }
            ),
            500,
        )


# API-Endpunkt zum Abrufen aller Kunden.
@app.route("/customers", methods=["GET"])
def get_customers():
    error_response = check_db_connection()
    if error_response:
        return error_response
    try:
        customers = []
        # Alle Kunden aus der Collection abrufen und konvertieren.
        for doc in kunden_collection.find({}):
            doc["_id"] = str(
                doc["_id"]
            )  # Konvertiert ObjectId zu String für JSON-Kompatibilität.
            customers.append(doc)
        return jsonify(customers)
    except Exception as e:
        print(f"Fehler in get_customers: {e}")
        return (
            jsonify(
                {
                    "error": "Interner Serverfehler beim Abrufen der Kunden",
                    "details": str(e),
                }
            ),
            500,
        )


# API-Endpunkt zum Erstellen einer neuen Lieferung.
@app.route("/create_delivery", methods=["POST"])
def create_delivery():
    error_response = check_db_connection()
    if error_response:
        return error_response
    data = request.json
    try:
        customer_name = data.get("customer")
        if not customer_name:
            return jsonify({"error": "Kundenname in der Anfrage fehlt."}), 400

        # Kunden anhand des Namens finden.
        customer = kunden_collection.find_one({"name": customer_name})
        if not customer:
            return jsonify({"error": f"Kunde '{customer_name}' nicht gefunden"}), 400

        # Generierung eines eindeutigen Sicherheitsschlüssels für die Lieferung.
        security_key = generate_security_key()
        delivery = {
            "customer_id": str(customer["_id"]),
            "adresse": customer.get("adresse", "Unbekannt"),
            "security_key": security_key,  # Der Sicherheitsschlüssel wird mit der Lieferung gespeichert.
            "status": "pending",  # Initialer Status der Lieferung.
        }
        # Lieferung in die Datenbank einfügen.
        delivery_id = lieferungen_collection.insert_one(delivery).inserted_id
        # Rückgabe der Liefer-ID und des Sicherheitsschlüssels an den Client.
        return jsonify({"delivery_id": str(delivery_id), "security_key": security_key})
    except Exception as e:
        print(f"Fehler in create_delivery: {e}")
        return (
            jsonify(
                {
                    "error": "Interner Serverfehler beim Erstellen der Lieferung",
                    "details": str(e),
                }
            ),
            500,
        )


# API-Endpunkt zum Aktualisieren des Lieferstatus (pending -> on route -> delivered).
@app.route("/update_status", methods=["POST"])
def update_status():
    error_response = check_db_connection()
    if error_response:
        return error_response
    data = request.json
    try:
        security_key = data.get("security_key")
        if not security_key:
            return jsonify({"error": "Sicherheitsschlüssel in der Anfrage fehlt."}), 400

        # Lieferung anhand des bereitgestellten Sicherheitsschlüssels finden und verifizieren.
        delivery = lieferungen_collection.find_one({"security_key": security_key})
        if not delivery:
            return (
                jsonify(
                    {"error": "Ungültiger Schlüssel oder Lieferung nicht gefunden"}
                ),
                400,
            )

        current_status = delivery["status"]
        # Logik zur Statusänderung basierend auf dem aktuellen Status.
        if current_status == "pending":
            new_status = "on route"
        elif current_status == "on route":
            new_status = "delivered"
        else:
            # Verhindert weitere Statusänderungen, wenn bereits zugestellt.
            return jsonify({"error": "Lieferung bereits zugestellt"}), 400

        # Aktualisiert den Status in der Datenbank.
        lieferungen_collection.update_one(
            {"_id": delivery["_id"]}, {"$set": {"status": new_status}}
        )
        return jsonify({"message": f"Status aktualisiert: {new_status}"})
    except Exception as e:
        print(f"Fehler in update_status: {e}")
        return (
            jsonify(
                {
                    "error": "Interner Serverfehler beim Aktualisieren des Status",
                    "details": str(e),
                }
            ),
            500,
        )


# API-Endpunkt zur Verifizierung einer Lieferung.
@app.route("/verify_delivery", methods=["POST"])
def verify_delivery():
    error_response = check_db_connection()
    if error_response:
        return error_response
    data = request.json
    try:
        security_key = data.get("security_key")
        if not security_key:
            return jsonify({"error": "Sicherheitsschlüssel in der Anfrage fehlt."}), 400

        # Lieferung anhand des bereitgestellten Sicherheitsschlüssels finden.
        delivery = lieferungen_collection.find_one({"security_key": security_key})
        if not delivery:
            return (
                jsonify(
                    {"error": "Ungültiger Schlüssel oder Lieferung nicht gefunden"}
                ),
                400,
            )

        # Prüfen, ob die Lieferung den Status "delivered" hat.
        if delivery["status"] != "delivered":
            return jsonify({"error": "Lieferung noch nicht abgeschlossen"}), 400

        return jsonify({"message": "Lieferung erfolgreich zugestellt"})
    except Exception as e:
        print(f"Fehler in verify_delivery: {e}")
        return (
            jsonify(
                {
                    "error": "Interner Serverfehler beim Verifizieren der Lieferung",
                    "details": str(e),
                }
            ),
            500,
        )


# API-Endpunkt zum Abrufen aller Lieferungen.
@app.route("/deliveries", methods=["GET"])
def get_deliveries():
    error_response = check_db_connection()
    if error_response:
        return error_response
    try:
        deliveries = []
        # Alle Lieferungen abrufen und IDs konvertieren.
        for doc in lieferungen_collection.find({}):
            doc["_id"] = str(doc["_id"])
            if "customer_id" in doc:
                doc["customer_id"] = str(doc["customer_id"])
            deliveries.append(doc)
        return jsonify(deliveries)
    except Exception as e:
        print(f"Fehler in get_deliveries: {e}")
        return (
            jsonify(
                {
                    "error": "Interner Serverfehler beim Abrufen der Lieferungen",
                    "details": str(e),
                }
            ),
            500,
        )


# Startpunkt der Flask-Anwendung.
if __name__ == "__main__":
    # Der Port wird von der Umgebungsvariable PORT (gesetzt von Render) gelesen.
    # Ein Fallback-Port (5001) wird für lokale Tests verwendet.
    port = int(os.environ.get("PORT", 5001))
    # debug=False für Produktionsumgebungen, host="0.0.0.0" für den Zugriff von außen.
    app.run(debug=False, host="0.0.0.0", port=port)
