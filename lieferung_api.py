import random
import string
import certifi
from pymongo import MongoClient
from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv  # Importiere load_dotenv

# Lade Umgebungsvariablen aus der .env-Datei
load_dotenv()

app = Flask(__name__)

client = None
db = None
kunden_collection = None
lieferungen_collection = None
geodaten_collection = None

try:
    # MongoDB URI aus Umgebungsvariable laden
    # Diese URI sollte den Datenbanknamen und die Query-Parameter enthalten
    mongo_uri = os.getenv("MONGO_URI")

    if not mongo_uri:
        raise ValueError(
            "MONGO_URI Umgebungsvariable ist nicht gesetzt. Bitte die .env-Datei prüfen."
        )

    print(f"Aktuelles Arbeitsverzeichnis: {os.getcwd()}")
    print(f"Verwendete Verbindungs-URI (aus .env, ohne tlsCAFile): {mongo_uri}")

    # MongoClient wird mit der URI und tlsCAFile als separatem Argument aufgerufen
    client = MongoClient(mongo_uri, tlsCAFile=certifi.where())

    client.admin.command("ping")
    print("Erfolgreich mit MongoDB Atlas verbunden!")

    # Die Datenbank "SmarthomeBox" sollte bereits in der MONGO_URI enthalten sein.
    # PyMongo wählt sie automatisch aus, wenn sie in der URI vorhanden ist.
    # Wir können sie zur Sicherheit auch explizit referenzieren.
    db = client["SmarthomeBox"]
    kunden_collection = db["kunden"]
    lieferungen_collection = db["lieferungen"]
    geodaten_collection = db["geodaten"]
    print("Datenbank 'SmarthomeBox' und Collections ausgewählt.")

except Exception as e:
    print(f"FEHLER: Probleme beim Aufbau der MongoDB-Verbindung: {e}")
    # Wenn db oder collections nicht initialisiert werden, setzen wir sie auf None
    # Dies ist wichtig, damit check_db_connection den Fehler abfangen kann
    db = None
    kunden_collection = None
    lieferungen_collection = None
    geodaten_collection = None


def generate_security_key():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


def check_db_connection():
    # Überprüft, ob die Collections initialisiert wurden.
    # Dies ist nun wichtiger, da die DB-Initialisierung fehlschlagen kann.
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


# Create new Customer via API
@app.route("/create_customer", methods=["POST"])
def create_customer():
    error_response = check_db_connection()
    if error_response:
        return error_response
    data = request.json
    # check if all needed fields have been passed
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
        if kunden_collection.find_one({"name": data["name"]}):
            return jsonify({"error": "Kunde mit diesem Namen existiert bereits"}), 409
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


@app.route("/customers", methods=["GET"])
def get_customers():
    error_response = check_db_connection()
    if error_response:
        return error_response
    try:
        customers = []
        for doc in kunden_collection.find({}):
            doc["_id"] = str(doc["_id"])
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
        customer = kunden_collection.find_one({"name": customer_name})
        if not customer:
            return jsonify({"error": f"Kunde '{customer_name}' nicht gefunden"}), 400

        security_key = generate_security_key()
        delivery = {
            "customer_id": str(customer["_id"]),
            "adresse": customer.get("adresse", "Unbekannt"),
            "security_key": security_key,
            "status": "pending",
        }
        delivery_id = lieferungen_collection.insert_one(delivery).inserted_id
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

        delivery = lieferungen_collection.find_one({"security_key": security_key})
        if not delivery:
            return (
                jsonify(
                    {"error": "Ungültiger Schlüssel oder Lieferung nicht gefunden"}
                ),
                400,
            )

        current_status = delivery["status"]
        if current_status == "pending":
            new_status = "on route"
        elif current_status == "on route":
            new_status = "delivered"
        else:
            return jsonify({"error": "Lieferung bereits zugestellt"}), 400

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

        delivery = lieferungen_collection.find_one({"security_key": security_key})
        if not delivery:
            return (
                jsonify(
                    {"error": "Ungültiger Schlüssel oder Lieferung nicht gefunden"}
                ),
                400,
            )

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


@app.route("/deliveries", methods=["GET"])
def get_deliveries():
    error_response = check_db_connection()
    if error_response:
        return error_response
    try:
        deliveries = []
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


if __name__ == "__main__":
    port = 5001
    app.run(debug=True, host="0.0.0.0", port=port)
