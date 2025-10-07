from flask import Flask, jsonify, request
import os
from pymongo import MongoClient


# GET MONGO URI FROM ENV.VARIABLE
MONGO_URI = os.environ.get("MONGO_URI")

# INITIALISE FLASK APP
app = Flask(__name__)


try:
    # LOAD MONGO DB CONNECTION FROM ENV.VARIABLE
    mongo_uri = os.getenv("MONGO_URI")

    # CHECK IF ENV VAIABLE IS SET
    if not mongo_uri:
        raise ValueError(
            "MONGO_URI Umgebungsvariable ist nicht gesetzt. Bitte in den Render Environment Variables prüfen."
        )

    print(
        f"Verbindungs-URI (aus Umgebungsvariable geladen): {mongo_uri.split('@')[0]}@...{mongo_uri.split('/')[-1]}"
    )

    # CONNECTION TO MONGO ATLAS
    client = MongoClient(mongo_uri)

    # TEST CONNECTION VIA PING
    client.admin.command("ping")
    print("Erfolgreich mit MongoDB Atlas verbunden!")

    # CHOOSE DB AND COLLECTION
    db = client["SmartHanger"]
    status_collection = db["Status"]
    print("DB & Collection selected.")


except Exception as e:
    print(f"FEHLER: Probleme beim Aufbau der MongoDB-Verbindung: {e}")


@app.route("/insert", methods=["POST"])
def set_status():
    if status_collection is None:
        return jsonify({"error": "No database connection"}), 500

    data = request.get_json()
    if not data or "status" not in data:
        return jsonify({"error": "Missing 'status' field"}), 400

    status_value = data["status"].lower()
    if status_value not in ["on", "off"]:
        return jsonify({"error": "Status must be 'on' or 'off'"}), 400

    try:
        result = status_collection.insert_one({"status": status_value})
        return (
            jsonify(
                {
                    "message": f"Status set to {status_value}",
                    "id": str(result.inserted_id),
                }
            ),
            201,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# CREATE API ENDPOINT TO UPDATE STATUS
@app.route("/update", methods=["PUT"])
def update_status():
    # CHECK IF DB CONNECTION EXISTS
    if status_collection is None:
        return jsonify({"error": "No database connection"}), 500
    # VAliDATE INPUT
    try:
        data = request.get_json(force=True)
        new_status = data.get("status", "off").lower()
        # VALIDATE STATUS VALUE
        if new_status not in ["on", "off"]:
            return jsonify({"error": "Status must be 'on' or 'off'"}), 400

        result = status_collection.update_one(
            {}, {"$set": {"status": new_status}}, upsert=True
        )

        if result.matched_count > 0:
            return jsonify({"message": f"Status updated to {new_status}"}), 200
        else:
            return jsonify({"message": f"Status set to {new_status}"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


#
#    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
