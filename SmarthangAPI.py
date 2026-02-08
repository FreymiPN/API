from flask import Flask, jsonify, request
import os
from pymongo import MongoClient
from datetime import datetime
import random  # necessary for 32bit user_id


# GET MONGO URI FROM ENV.VARIABLE
MONGO_URI = os.environ.get("MONGO_URI")

# INITIALISE FLASK APP
app = Flask(__name__)


try:
    mongo_uri = os.getenv("MONGO_URI")

    if not mongo_uri:
        raise ValueError("MONGO_URI Umgebungsvariable ist nicht gesetzt. Bitte in den Render Environment Variables prüfen.")

    print(f"Connection-URI: {mongo_uri.split('@')[0]}@...{mongo_uri.split('/')[-1]}")

    client = MongoClient(mongo_uri)
    client.admin.command("ping")
    print("Successfully connected to MongoDB Atlas!")

    db = client["SmartHanger"]
    customers_collection = db["Customers"]
    status_collection = db["Status"]
    logs_collection = db["logs"]

    print("DB & Collection selected.")

except Exception as e:
    print(f"ERROR: Database connection failed: {e}")
    customers_collection = None
    status_collection = None
    logs_collection = None


# ------- START API ENDPOINTS ------- #


@app.route("/create_customer", methods=["POST"])
def create_customer():
    if customers_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

    try:
        data = request.get_json(force=True)
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        email = data.get("email")

        if not first_name or not email:
            return jsonify({"error": "BAD_REQUEST: Missing first_name or email"}), 400

        while True:
            new_user_id = random.randint(1, 2**16 - 1)
            if not customers_collection.find_one({"user_id": new_user_id}):
                break

        customer_doc = {
            "user_id": new_user_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "registration_date": datetime.now(),
            "hangers": [],
        }

        customers_collection.insert_one(customer_doc)
        return jsonify({"message": "Customer created", "user_id": new_user_id}), 201

    except Exception:
        return jsonify({"error": "INTERNAL SERVER ERROR"}), 500


@app.route("/assign_hanger", methods=["POST"])
def assign_hanger():
    if customers_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

    try:
        data = request.get_json(force=True)
        user_id = data.get("user_id")
        hanger_id = data.get("hanger_id")

        if user_id is None or hanger_id is None:
            return jsonify({"error": "BAD_REQUEST: user_id and hanger_id required"}), 400

        hanger_id_int = int(hanger_id)
        if not (1 <= hanger_id_int <= 2**16 - 1):
            return jsonify({"error": "BAD_REQUEST: Hanger ID out of range"}), 400

        hanger_obj = {
            "hanger_id": hanger_id_int,
            "status": "off",
            "paired_at": datetime.now(),
        }

        result = customers_collection.update_one(
            {"user_id": int(user_id)},
            {"$addToSet": {"hangers": hanger_obj}},
        )

        if result.matched_count == 0:
            return jsonify({"error": "NOT_FOUND: User not found"}), 404

        if result.modified_count == 0:
            return jsonify({"message": "ALREADY_REPORTED: Hanger already paired"}), 200

        return jsonify({"message": "OK: Hanger paired"}), 200

    except ValueError:
        return jsonify({"error": "BAD_REQUEST: Invalid IDs"}), 400
    except Exception:
        return jsonify({"error": "INTERNAL SERVER ERROR"}), 500


@app.route("/update_status", methods=["PUT"])
def update_status():
    if customers_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

    try:
        data = request.get_json(force=True)
        user_id = data.get("user_id")
        hanger_id = data.get("hanger_id")
        status = (data.get("status") or "").lower()

        allowed = ["off", "on", "heating", "drying"]
        if status not in allowed:
            return jsonify({"error": f"BAD_REQUEST: Allowed {allowed}"}), 400

        result = customers_collection.update_one(
            {"user_id": int(user_id), "hangers.hanger_id": int(hanger_id)},
            {"$set": {"hangers.$.status": status, "hangers.$.last_updated": datetime.now()}},
        )

        if result.matched_count == 0:
            return jsonify({"error": "NOT_FOUND"}), 404

        return jsonify({"message": "OK: Status updated"}), 200

    except Exception:
        return jsonify({"error": "INTERNAL SERVER ERROR"}), 500


# --------- UPDATED PART (temp + hum) ---------


@app.route("/log_temp", methods=["POST"])
def log_temperature():
    if logs_collection is None or customers_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

    try:
        data = request.get_json(force=True)

        hanger_id = data.get("hanger_id")
        temp = data.get("temp")
        hum = data.get("hum")

        if hanger_id is None or temp is None or hum is None:
            return jsonify({"error": "BAD_REQUEST: hanger_id, temp and hum required"}), 400

        hanger_id_int = int(hanger_id)
        temp_float = float(temp)
        hum_float = float(hum)

        if not (0 <= hanger_id_int <= 2**16 - 1):
            return jsonify({"error": "BAD_REQUEST: Hanger ID out of range"}), 400

        owner = customers_collection.find_one({"hangers.hanger_id": hanger_id_int})
        if not owner:
            return jsonify({"error": "NOT_FOUND: Hanger not paired"}), 404

        log_entry = {
            "user_id": owner["user_id"],
            "hanger_id": hanger_id_int,
            "temp": temp_float,
            "hum": hum_float,
            "timestamp": datetime.now(),
        }

        logs_collection.insert_one(log_entry)
        return jsonify({"message": "CREATED: Log stored"}), 201

    except ValueError:
        return jsonify({"error": "BAD_REQUEST: Invalid data types"}), 400
    except Exception:
        return jsonify({"error": "INTERNAL SERVER ERROR"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
