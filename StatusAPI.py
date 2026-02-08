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
    # LOAD MONGO DB CONNECTION FROM ENV.VARIABLE
    mongo_uri = os.getenv("MONGO_URI")

    # CHECK IF ENV VARIABLE IS SET
    if not mongo_uri:
        raise ValueError("MONGO_URI Umgebungsvariable ist nicht gesetzt. Bitte in den Render Environment Variables prüfen.")

    # Optional: print shortened URI
    print(f"Connection-URI: {mongo_uri.split('@')[0]}@...{mongo_uri.split('/')[-1]}")

    # CONNECTION TO MONGO ATLAS
    client = MongoClient(mongo_uri)

    # TEST CONNECTION VIA PING
    client.admin.command("ping")
    print("Successfully connected to MongoDB Atlas!")

    # CHOOSE DB AND COLLECTIONS
    db = client["SmartHanger"]

    # FIX: customers_collection was missing (this caused VS Code warnings)
    customers_collection = db["Customers"]  # confirmed by you ✅
    status_collection = db["Status"]
    logs_collection = db["logs"]

    print("DB & Collections selected.")

except Exception as e:
    print(f"ERROR: Database connection failed: {e}")
    customers_collection = None
    status_collection = None
    logs_collection = None


# ------- START API ENDPOINTS ------- #
# 1. API ENDPOINT TO CREATE CUSTOMER
@app.route("/create_customer", methods=["POST"])
def create_customer():
    if customers_collection is None:
        return jsonify({"error": "No database connection"}), 500

    try:
        data = request.get_json(force=True)
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        email = data.get("email")

        if not first_name or not email:
            return jsonify({"error": "Missing required fields: first_name or email"}), 400

        # Generate random 32bit user_id
        new_user_id = random.randint(1, 2**32 - 1)  # max 32bit integer

        customer_doc = {
            "user_id": new_user_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "registration_date": datetime.now(),
            "hangers": [],  # hangers will be linked later via App
        }

        customers_collection.insert_one(customer_doc)
        return jsonify({"message": "Customer created", "user_id": new_user_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 3. API ENDPOINT TO UPDATE STATUS (via App)
# App sends: {"user_id": 12345, "hanger_id": 1024, "status": "drying"}
@app.route("/update_status", methods=["PUT"])
def update_status():
    if customers_collection is None:
        return jsonify({"error": "No database connection"}), 500

    try:
        data = request.get_json(force=True)

        user_id = data.get("user_id")
        hanger_id = data.get("hanger_id")
        new_status = (data.get("status") or "").lower()

        if user_id is None or hanger_id is None:
            return jsonify({"error": "Missing user_id or hanger_id"}), 400

        allowed_statuses = ["inactive", "active", "heating", "drying", "on", "off"]
        if new_status not in allowed_statuses:
            return jsonify({"error": f"Invalid status. Allowed: {allowed_statuses}"}), 400

        filter_query = {
            "user_id": int(user_id),
            "hangers.hanger_id": int(hanger_id),
        }

        update_action = {
            "$set": {
                "hangers.$.status": new_status,
                "hangers.$.last_updated": datetime.now(),
            }
        }

        result = customers_collection.update_one(filter_query, update_action)

        if result.matched_count > 0:
            return jsonify({"message": f"Status updated to {new_status}"}), 200

        return jsonify({"error": "User not found or Hanger not paired to this user."}), 404

    except ValueError:
        return jsonify({"error": "IDs must be integers"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 4. LOG SENSOR DATA (Temperature + Humidity from Hardware)
# Hardware sends: {"hanger_id": 1024, "temp": 45.5, "hum": 52.1}
@app.route("/log_temp", methods=["POST"])
def log_temperature():
    if logs_collection is None or customers_collection is None:
        return jsonify({"error": "No database connection"}), 500

    try:
        data = request.get_json(force=True)

        hanger_id = data.get("hanger_id")
        temp = data.get("temp")
        hum = data.get("hum")

        if hanger_id is None or temp is None or hum is None:
            return jsonify({"error": "Missing required fields: hanger_id, temp, hum"}), 400

        try:
            hanger_id_int = int(hanger_id)
            temp_float = float(temp)
            hum_float = float(hum)

            # Safety check: 16-bit Hanger ID range
            if not (0 <= hanger_id_int <= 2**16 - 1):
                return jsonify({"error": "Hanger ID out of valid 16-bit range"}), 400

            # Optional sanity checks (adjust if your sensor behaves differently)
            if not (-40.0 <= temp_float <= 125.0):
                return jsonify({"error": "temp out of expected range (-40..125)"}), 400

            if not (0.0 <= hum_float <= 100.0):
                return jsonify({"error": "hum out of expected range (0..100)"}), 400

            # LOOKUP OWNER
            owner = customers_collection.find_one({"hangers.hanger_id": hanger_id_int})
            if not owner:
                return jsonify({"error": f"Hanger {hanger_id_int} is not paired to any user. Data ignored."}), 404

            user_id_int = owner["user_id"]

            log_entry = {
                "user_id": user_id_int,
                "hanger_id": hanger_id_int,
                "temp": temp_float,
                "hum": hum_float,
                "timestamp": datetime.now(),
            }

        except ValueError:
            return jsonify({"error": "Data type error: hanger_id must be int, temp/hum must be float"}), 400

        result = logs_collection.insert_one(log_entry)
        return jsonify({"message": "Log entry created", "id": str(result.inserted_id)}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # For Render you usually run with gunicorn, but this is fine for local tests
    app.run(debug=True, host="0.0.0.0", port=5001)
