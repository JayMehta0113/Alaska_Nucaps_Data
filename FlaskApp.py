from flask import Flask, request, render_template, jsonify, Response, session, redirect, url_for, g #
from concurrent.futures import ThreadPoolExecutor
from flask_session import Session
import boto3 #
from botocore.config import Config
from botocore import UNSIGNED
import xarray as xr #
import os
import zipfile
import io
import threading
import matplotlib
from gridding import Radiance_gridding, AOD_gridding
import re
import redis 
import secrets
import json
from utils import list_all_files, open_s3_dataset, filter_data


app = Flask(__name__)

# Setting up session
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-secret-key")
Session(app)

redis_client = redis.StrictRedis(host="localhost", port=6379, decode_responses=True)

global_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=5)

def get_redis_connection():
    #per request redis connection
    if 'redis' not in g:
        g.redis = redis.StrictRedis(host='localhost', port=6379, decode_responses=True)
    return g.redis

def get_user_cache():
    """Retrieve or initialize user cache in Redis."""
    cache_key = session.get("cache_key")
    if not cache_key:
        cache_key = "cache_" + secrets.token_urlsafe(8)
        session["cache_key"] = cache_key
        redis_client.setex(cache_key, 43200, '{"progress": {}, "results": []}')
    user_cache = redis_client.get(cache_key)
    if user_cache is None:
        user_cache = {"progress": {}, "results": []}
        redis_client.setex(cache_key, 43200, str(user_cache))
    return eval(user_cache)

def update_user_cache(cache_key, data):
    """Update user cache in Redis."""
    redis_client.setex(cache_key, 43200, str(data))

def get_stop_key():
    """Generate or retrieve the stop key for the current session."""
    stop_key = session.get("stop_key")
    if not stop_key:
        stop_key = "stop_" + secrets.token_urlsafe(8)
        session["stop_key"] = stop_key
        redis_client.setex(stop_key, 43200, "false")  # Initialize stop_requested to false with TTL of 12 hours
    return stop_key

def get_stop_flag(stop_key):
    """Check the stop_requested flag in the Redis stop key."""
    return redis_client.get(stop_key) == "true"

def set_stop_flag(stop_key, value):
    """Set the stop_requested flag in the Redis stop key."""
    redis_client.setex(stop_key, 43200, "true" if value else "false")

# ---------- Processing Files --------------
def process_files(data, cache_key, stop_key):
    with global_lock:
        try:
            cached_data = eval(redis_client.get(cache_key))
            progress = cached_data["progress"]
            results = cached_data["results"]
            #stop_key = get_stop_key() 
        except Exception as e:
            print(f"error: {e}")

        # Initialize progress
        bucket_name = "noaa-jpss"
        prefix = f"NOAA20/SOUNDINGS/NOAA20_NUCAPS-CCR/{data['year']}/{str(data['month']).zfill(2)}/{str(data['day']).zfill(2)}/"
        client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

        print(f"Fetching file keys from bucket: {bucket_name} with prefix: {prefix}")
        file_keys = list_all_files(bucket_name, prefix, client_s3)
        print(f"Total file keys retrieved: {len(file_keys)}")

        if not file_keys:
            progress["status"] = "no_files"
            progress["running"] = False
            update_user_cache(cache_key, {"progress": progress, "results": results})
            print("no file keys")
            return

        progress.update({
            "status": "in_progress",
            "total_files": len(file_keys),
            "files_processed": 0,
        })
        update_user_cache(cache_key, {"progress": progress, "results": results})

        try:
            for key in file_keys:
                print("loop running")
                if get_stop_flag(stop_key):
                    print("stop flag detected")
                    progress.update({"status": "stopped", "running": False})
                    update_user_cache(cache_key, {"progress": progress, "results": results})
                    return

                # Process the file
                dataset = open_s3_dataset(bucket_name, key, client_s3)
                filtered = filter_data(
                    dataset,
                    lat_min=data['lat_min'],
                    lat_max=data['lat_max'],
                    long_min=data['long_min'],
                    long_max=data['long_max'],
                )

                # Update results
                if filtered and not any(result["file"] == key for result in results):
                    results.append({"file": key, **filtered})
                    print("added files")

                progress["files_processed"] += 1
                update_user_cache(cache_key, {"progress": progress, "results": results})
        except Exception as e:
            print(f"Error in process_files: {e}")

        progress.update({"status": "completed", "running": False})
        update_user_cache(cache_key, {"progress": progress, "results": results})




def find_aresol_file(data, cache_key, stop_key):

    with global_lock:

        cached_data = eval(redis_client.get(cache_key))
        progress = cached_data["progress"]
        results = cached_data["results"]

        bucket_name = 'noaa-cdr-aerosol-optical-thickness-pds'
        prefix = f"data/daily/{str(data['year'])}"

        client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

        try:
            file_keys = list_all_files(bucket_name, prefix, client_s3)

            if not file_keys:
                return f"no files found under {prefix}"
            
            # Create the search pattern based on the year, month, and day
            search_pattern = f"{str(data['year'])}{str(data['month']).zfill(2)}{str(data['day']).zfill(2)}"
            print(f"Searching for files containing: {search_pattern}")

            # Loop through all files and check if the search pattern is in the key
            for file_key in file_keys:
                #print(file_key)

                # Using a regular expression to ensure we don't match the added date at the end
                # Example regex: A file name might end with "_cYYYYMMDD.nc", we want to avoid that
                # This regex captures the part of the filename up until the added date
                if re.search(rf'-avg_{search_pattern}(?=_)', file_key):
                    results.append(file_key)
                    print("key found")
                    progress.update({"found_file": True, "status": "complete", "files_processed": 1})
                    update_user_cache(cache_key, {"progress": progress, "results": results})
                    return
        
        except Exception as e:
            return f"error searching for file: {e}"

# --------- endpoints ------------

@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")

@app.route('/select_dataset', methods=['POST'])
def select_dataset():
    dataset = request.form.get('dataset')
    if dataset == 'cris_radiances':
        return redirect(url_for('cris_radiances'))
    elif dataset == 'aerosol_depth':
        return redirect(url_for('aerosol_depth'))
    return redirect(url_for('index'))

@app.route('/cris_radiances')
def cris_radiances():
    return render_template('cris_radiances.html')

@app.route('/aerosol_depth')
def aerosol_depth():
    return render_template('aerosol_depth.html')

@app.route("/start_query", methods=["POST"])
def start_query():
    data = request.json
    cache_key = session.get("cache_key") or "cache_" + secrets.token_urlsafe(8)
    session["cache_key"] = cache_key
    stop_key = get_stop_key()  # Create stop key for the session

    redis_client.setex(cache_key, 43200, str({"progress": {}, "results": []}))  # Initialize cache
    user_cache = eval(redis_client.get(cache_key))

    user_cache["progress"] = {
        "total_files": 0,
        "files_processed": 0,
        "status": "not_started",
        "running": True,
        "bucket": data["Datasets"],
        "found_file": False,
    }
    user_cache["results"] = []
    update_user_cache(cache_key, user_cache)

    set_stop_flag(stop_key, False)  # Reset the stop flag to False for a new query

    if data['Datasets'] == 'aerosol_depth':
        executor.submit(find_aresol_file, data, cache_key, stop_key)
    elif data['Datasets'] == 'cris_radiances':
        executor.submit(process_files, data, cache_key, stop_key)

    return jsonify({"message": "Processing started"})

@app.route("/stop_query", methods=["POST"])
def stop_query():
    stop_key = get_stop_key()
    if get_stop_flag(stop_key):
        return jsonify({"message": "Query already stopping..."}), 200

    set_stop_flag(stop_key, True)
    print(f"Stop flag set for {stop_key}")
    return jsonify({"message": "Query stopping..."}), 200

@app.route("/get_progress", methods=["GET"])
def get_progress():
    cache_key = session.get("cache_key")
    user_cache = eval(redis_client.get(cache_key))
    stop_key = get_stop_key()
    stop_requested = get_stop_flag(stop_key)

    return jsonify({
        "progress": user_cache["progress"],
        "results": user_cache["results"],
        "stop_requested": stop_requested,
    })


    
# ------------ Added features ------------ 

@app.route("/download_all_files", methods=["GET"])
def download_all_files():
    """Create a ZIP archive dynamically and send it to the user."""
    user_cache = get_user_cache()
    bucket_name = "noaa-jpss"
    client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    zip_buffer = io.BytesIO() 

    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            user_cache = get_user_cache()
            for result in user_cache["results"]:
                file_name = result["file"]
                try:
                    response = client_s3.get_object(Bucket=bucket_name, Key=file_name)
                    file_content = response["Body"].read()

                    # Add the file to the ZIP archive
                    zip_file.writestr(file_name.split("/")[-1], file_content)
                except Exception as e:
                    print(f"Error fetching file {file_name}: {e}")
                    continue

        # Prepare the ZIP file for download
        zip_buffer.seek(0)
        return Response(
            zip_buffer,
            mimetype="application/zip",
            headers={"Content-Disposition": "attachment; filename=matching_files.zip"}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

matplotlib.use('agg') 
@app.route("/grid_and_render", methods=["POST"])
def grid_and_render():
    """Grid data using files from the results list and return a map as a binary PNG."""
    
    user_cache = get_user_cache()

    print('made it to grid route')

    try:
        """bucket is named/files are pulled inside of specific gridding class to allow for this fucntion 
        to act dynamically with multiple buckets""" 

        if not user_cache["results"]:
            return jsonify({"error": "No files available in results for gridding"}), 400
        
        data = request.json

        print('made it past checking if results exist/setting data variable')

        if(user_cache["progress"]["bucket"] == "cris_radiances"):
            print("radiance if statement")
            try:
                # Call the gridding function
                plot_png = Radiance_gridding.process_and_grid(
                    user_cache["results"], data)
            except:
                print("radiance gridding doesnt work")
            
            # Return the PNG image
            return Response(plot_png, mimetype="image/png")

        elif(user_cache["progress"]["bucket"] == "aerosol_depth"):
            print('AOD if statement')
            try:
                plot_png = AOD_gridding.grid_aresol_data(user_cache["results"])
            except:
                print("AOD gridding doesnt work")

            return Response(plot_png, mimetype="image/png")

    except Exception as e:
        print(f"Error during gridding: {e}")
        return jsonify({"error": str(e)}), 500

@app.teardown_appcontext
def close_redis(error):
    """Cleanup Redis connection"""
    redis_conn = g.pop('redis', None)
    if redis_conn is not None:
        redis_conn.close()

if __name__ == "__main__":
    app.run(port=8000, debug=True, threaded=True)