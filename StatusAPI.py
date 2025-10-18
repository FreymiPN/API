from flask import Flask, jsonify, request
import os
from pymongo import MongoClient
from bson.objectid import ObjectId  # convert string id to ObjectId type


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
        return jsonify({"error": "No database connection"}), 503

    # VALIDATE INPUT
    try:
        # force=True is used to parse the request body even if the MIME type
        # is not correctly set by the client (e.g., in some test environments)
        data = request.get_json(force=True)

        # 1. EXTRACT ID AND STATUS
        # We need the _id to filter the document. If it's missing, we cannot update a specific status.
        document_id_str = data.get("_id")
        # Use empty string as default, must be explicitly provided
        new_status = data.get("status", "").lower()

        # 2. VALIDATE REQUIRED FIELDS
        if not document_id_str:
            return jsonify({"error": "Missing '_id' field for targeted update"}), 400
        if new_status not in ["on", "off"]:
            return jsonify({"error": "Status must be 'on' or 'off'"}), 400

        # 3. CREATE FILTER QUERY
        # Convert the received string ID into a MongoDB ObjectId type for correct filtering.
        try:
            document_id_obj = ObjectId(document_id_str)
        except:
            return (
                jsonify(
                    {
                        "error": "Invalid '_id' format. Must be a valid 24-character hex string."
                    }
                ),
                400,
            )

        # Define the filter to find the specific document by its ObjectId
        filter_query = {"_id": document_id_obj}

        # Define the update action (what to change)
        update_action = {"$set": {"status": new_status}}

        # Execute the update operation
        # NOTE: If the ID does not exist, this will not create a new document
        # because upsert=True is omitted.
        result = status_collection.update_one(
            filter_query,  # ARG 1: The document to find (based on the sent ID)
            update_action,  # ARG 2: The fields to update
        )

        if result.matched_count > 0:
            # Document was found and updated
            return (
                jsonify(
                    {
                        "message": f"Status for ID {document_id_str} updated to {new_status}"
                    }
                ),
                200,
            )
        else:
            # Document was not found
            return (
                jsonify({"message": f"Document with ID {document_id_str} not found."}),
                404,
            )

    except Exception as e:
        print(f"Update error: {e}")
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
