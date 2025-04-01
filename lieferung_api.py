import random
import string
import certifi
from pymongo import MongoClient
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Verbindung zur Datenbank
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())

# Aufrufen der Datenbank und Cluster
db = client["SmarthomeBox"]
kunden_collection = db["kunden"]
lieferungen_collection = db["lieferungen"]
geodaten_collection = db["geodaten"]


# Funktion zur Generierung eines Sicherheitsschlüssels
def generate_security_key():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


# Lieferung erstellen
@app.route("/create_delivery", methods=["POST"])
def create_delivery():
    data = request.json
    customer = kunden_collection.find_one({"name": data["customer"]})
    if not customer:
        return jsonify({"error": "Kunde nicht gefunden"}), 400

    # Dummy-Geolocation für Tests
    geolocation = {"adresse": customer["adresse"], "latitude": 0.0, "longitude": 0.0}

    # Generiere den Sicherheitsschlüssel
    security_key = generate_security_key()
    delivery = {
        "customer_id": customer["_id"],
        "adresse": customer["adresse"],
        "security_key": security_key,
        "status": "pending",
    }

    # Füge Lieferung zur Datenbank hinzu
    delivery_id = lieferungen_collection.insert_one(delivery).inserted_id
    return jsonify({"delivery_id": str(delivery_id), "security_key": security_key})


# Status-Update für Lieferung (pending → on route → delivered)
@app.route("/update_status", methods=["POST"])
def update_status():
    data = request.json
    delivery = lieferungen_collection.find_one({"security_key": data["security_key"]})

    if not delivery:
        return jsonify({"error": "Ungültiger Schlüssel"}), 400

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


# Lieferung verifizieren via API
@app.route("/verify_delivery", methods=["POST"])
def verify_delivery():
    data = request.json
    delivery = lieferungen_collection.find_one({"security_key": data["security_key"]})

    if not delivery:
        return jsonify({"error": "Ungültiger Schlüssel"}), 400

    if delivery["status"] != "delivered":
        return jsonify({"error": "Lieferung noch nicht abgeschlossen"}), 400

    return jsonify({"message": "Lieferung erfolgreich zugestellt"})


# Admin-Funktion: Alle Lieferungen abrufen
@app.route("/deliveries", methods=["GET"])
def get_deliveries():
    deliveries = list(lieferungen_collection.find({}, {"_id": 0}))
    return jsonify(deliveries)


if __name__ == "__main__":
    app.run(debug=True)
