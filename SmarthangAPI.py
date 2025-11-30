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

    # CHECK IF ENV VAIABLE IS SET
    if not mongo_uri:
        raise ValueError("MONGO_URI Umgebungsvariable ist nicht gesetzt. Bitte in den Render Environment Variables prüfen.")
    print(f"Connection-URI: {mongo_uri.split('@')[0]}@...{mongo_uri.split('/')[-1]}")

    # CONNECTION TO MONGO ATLAS
    client = MongoClient(mongo_uri)
    # TEST CONNECTION VIA PING
    client.admin.command("ping")
    print("Successfully connected to MongoDB Atlas!")

    # CHOOSE DB AND COLLECTION
    db = client["SmartHanger"]
    # customers_collection = db
    status_collection = db["Status"]
    logs_collection = db["logs"]
    customers_collection = db["Customers"]
    print("DB & Collection selected.")

except Exception as e:
    print(f"ERROR: Database connection failed: {e}")
    customers_collection = None
    logs_collection = None


# ------- START API ENDPOINTS ------- #
# 1. API ENDPOINT TO CREATE CUSTOMER
@app.route("/create_customer", methods=["POST"])
def create_customer():
    if customers_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

    try:
        data = request.get_json()
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        email = data.get("email")

        if not first_name or not email:
            return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

        # Generate random 32bit user_id
        while True:
            new_user_id = random.randint(1, 2**16 - 1)  # max 16bit integer, avoid 0
            existing_user = customers_collection.find_one({"user_id": new_user_id})  # check for unique user_id
            if not existing_user:
                break

        customer_doc = {
            "user_id": new_user_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "registration_date": datetime.now(),
            "hangers": [],  # empty list, hangers will be linked via APP which will trigger the hanger_id to be added
        }

        customers_collection.insert_one(customer_doc)
        return jsonify({"message": "Customer created", "user_id": new_user_id}), 201

    except Exception as e:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500


# 2. API ENDPOINT TO ASSIGN HANGER TO CUSTOMER
@app.route("/assign_hanger", methods=["POST"])
def assign_hanger():
    if customers_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        hanger_id = data.get("hanger_id")

        if not user_id or hanger_id is None:  # 0 can be a valid id, so check explicitly for None, check and remove if not needed
            return jsonify({"error": "BAD_REQUEST: Please provide user_id and hanger_id"}), 400

        # Validate Hanger ID (16-bit Unsigned Integer: 1 to 65535)
        try:
            hanger_id_int = int(hanger_id)
            if not (1 <= hanger_id_int <= 2**16 - 1):
                return (jsonify({"error": "BAD_REQUEST: Hanger ID out of 16-bit range (1-65535)"}), 400)
        except ValueError:
            return jsonify({"error": "BAD_REQUEST: Hanger ID must be an integer"}), 400

        # Create the hanger object to store in the user's profile
        new_hanger_object = {
            "hanger_id": hanger_id_int,  # Storing as INT now (has to be consistent with update logic)
            "status": "off",  # always default status after pairing
            "paired_at": datetime.now(),
        }

        # Update the customer document, $addToSet ensures we don't add the exact same hanger object twice
        result = customers_collection.update_one({"user_id": int(user_id)}, {"$addToSet": {"hangers": new_hanger_object}})

        if result.matched_count > 0:
            if result.modified_count > 0:
                return (jsonify({"message": f"OK: Hanger {hanger_id_int} paired to User {user_id}"}), 200)
            else:
                return jsonify({"message": "ALREADY_REPORTED: Hanger was already paired."}), 200
        else:
            return jsonify({"error": f"NOT_FOUND: User with user_id {user_id} not found."}), 404

    except ValueError:
        return jsonify({"error": "BAD_REQUEST: user_id must be an integer"}), 400
    except Exception as e:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500


# 3. API ENDPOINT TO UPDATE STATUS (via App)
# App sends: {"user_id": 12345, "hanger_id": 1024, "status": "drying"}
@app.route("/update_status", methods=["PUT"])
def update_status():
    if customers_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

    try:
        # force=True ensures parsing even if Content-Type header is missing
        data = request.get_json(force=True)

        user_id = data.get("user_id")
        hanger_id = data.get("hanger_id")
        new_status = data.get("status", "").lower()

        if not user_id or hanger_id is None:
            return jsonify({"error": "BAD_REQUEST: Missing user_id or hanger_id"}), 400

        # Extended status list as requested
        allowed_statuses = ["off", "on", "heating", "drying"]
        if new_status not in allowed_statuses:
            return (jsonify({"error": f"BAD_REQUEST: Invalid status. Allowed: {allowed_statuses}"}), 400)

        # THE UPDATE LOGIC:
        # 1. Filter: Find user by ID AND matching hanger_id (as INT) in the array
        filter_query = {
            "user_id": int(user_id),
            "hangers.hanger_id": int(hanger_id),  # Using INT for comparison
        }

        # 2. Update: Change status of THAT specific hanger in the array ($)
        update_action = {
            "$set": {
                "hangers.$.status": new_status,
                "hangers.$.last_updated": datetime.now(),
            }
        }

        result = customers_collection.update_one(filter_query, update_action)

        if result.matched_count > 0:
            return jsonify({"message": f"OK: Status updated to {new_status}"}), 200
        else:
            return (jsonify({"error": "NOT FOUND: User not found or Hanger not paired to this user."}), 404)

    except ValueError:
        return jsonify({"error": "BAD_REQUEST: IDs must be integers"}), 400
    except Exception as e:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500


# 4. LOG TEMPERATURE (Data from Hardware)
# Hardware sends: {"hanger_id": 1024, "temperature": 45.5}, KIM:  API looks it up in the DB.
@app.route("/log_temp", methods=["POST"])
def log_temperature():
    if logs_collection is None:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500

    try:
        data = request.get_json()

        # Hardware only sends ID and temperature
        hanger_id = data.get("hanger_id")
        temperature = data.get("temperature")

        # Check for missing fields
        if hanger_id is None or temperature is None:
            return jsonify({"error": "BAD_REQUEST: Missing required fields: hanger_id or temperature"}), 400

        try:
            # Type Conversion
            hanger_id_int = int(hanger_id)
            temp_float = float(temperature)

            # Safety check: 16-bit Hanger ID range
            if not (0 <= hanger_id_int <= 2**16 - 1):
                return jsonify({"error": "BAD_REQUEST: Hanger ID out of valid 16-bit range"}), 400

            # 1. LOOKUP OWNER: Find the customer who has this hanger in their list
            # query the 'Customers' collection looking for the specific hanger_id inside the 'hangers' array
            owner = customers_collection.find_one({"hangers.hanger_id": hanger_id_int})
            if not owner:
                return (jsonify({"error": f"NOT_FOUND: Hanger {hanger_id_int} is not paired to any user"}), 404)

            # 2. Extract the User ID from the found owner document
            user_id_int = owner["user_id"]

            log_entry = {
                "user_id": user_id_int,  # Inserted by API based on lookup
                "hanger_id": hanger_id_int,
                "temperature": temp_float,
                "timestamp": datetime.now(),
            }

        except ValueError:
            return jsonify({"error": "BAD_REQUEST: hanger_id must be int, temp must be float"}), 400

        result = logs_collection.insert_one(log_entry)

        return jsonify({"message": "CREATED: Log entry created", "id": str(result.inserted_id)}), 201

    except Exception as e:
        return jsonify({"error": "INTERNAL SERVER ERROR: No database connection"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
