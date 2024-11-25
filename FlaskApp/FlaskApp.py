from flask import Flask, request, render_template, jsonify, Response
import boto3
from botocore.config import Config
from botocore import UNSIGNED
import xarray as xr
import os
import zipfile
import io
import threading
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import matplotlib
import gridding as gridding

app = Flask(__name__)

# Global variables for results and progress
results = []
progress = {"total_files": 0, "files_processed": 0}

def open_s3_dataset(bucket, key, client_s3):
    """Open a dataset from S3."""
    response = client_s3.get_object(Bucket=bucket, Key=key)
    data = response["Body"].read()
    data_io = io.BytesIO(data)
    return xr.open_dataset(data_io, engine="h5netcdf", chunks={}, decode_times=False)

def filter_data(dataset, lat_min, lat_max, long_min, long_max):
    """Filter dataset based on latitude and longitude."""
    lat_mask = ((dataset["CrIS_Latitude"] >= lat_min) & (dataset["CrIS_Latitude"] <= lat_max)).compute()
    long_mask = ((dataset["CrIS_Longitude"] >= long_min) & (dataset["CrIS_Longitude"] <= long_max)).compute()
    combined_mask = lat_mask & long_mask
    filtered_data = dataset.where(combined_mask, drop=True)

    if filtered_data["CrIS_Latitude"].size > 0:
        return {
            "lat_min": float(filtered_data["CrIS_Latitude"].min().values),
            "lat_max": float(filtered_data["CrIS_Latitude"].max().values),
            "long_min": float(filtered_data["CrIS_Longitude"].min().values),
            "long_max": float(filtered_data["CrIS_Longitude"].max().values),
        }
    return None

def list_all_files(bucket_name, prefix, client_s3):
    """List all files in S3 bucket."""
    file_keys = []
    continuation_token = None
    while True:
        if continuation_token:
            response = client_s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=continuation_token)
        else:
            response = client_s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        file_keys.extend([obj["Key"] for obj in response.get("Contents", [])])
        if response.get("IsTruncated"):
            continuation_token = response["NextContinuationToken"]
        else:
            break
    return file_keys

def process_files(data):
    """Background function to process files."""
    global results, progress

    bucket_name = "noaa-jpss"
    prefix = f"NOAA20/SOUNDINGS/NOAA20_NUCAPS-CCR/{data['year']}/{str(data['month']).zfill(2)}/{str(data['day']).zfill(2)}/"

    client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    file_keys = list_all_files(bucket_name, prefix, client_s3)

    if not file_keys:
        progress["status"] = "no_files"
        progress["running"] = False
        return

    progress["status"] = "in_progress"
    progress["total_files"] = len(file_keys)
    progress["files_processed"] = 0
    progress["stop_requested"] = False  

    for key in file_keys:
        if progress["stop_requested"]:  # Check if stop is requested
            progress["status"] = "stopped"
            progress["running"] = False
            return

        dataset = open_s3_dataset(bucket_name, key, client_s3)
        filtered = filter_data(dataset, lat_min=51, lat_max=71, long_min=-175, long_max=-141)
        if filtered:
            if not any(result["file"] == key for result in results):  # Avoid duplicates
                results.append({"file": key, **filtered})
        progress["files_processed"] += 1

    progress["status"] = "completed"
    progress["running"] = False



@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")

@app.route("/start_query", methods=["POST"])
def start_query():
    """Start processing files."""
    global results, progress

    # Check if a process is already running
    if progress.get("running", False):
        return jsonify({"message": "Processing is already running. Please wait for it to complete."}), 400

    # Reset progress and results for a new query
    results.clear()
    progress = {"total_files": 0, "files_processed": 0, "status": "not_started", "running": True}

    data = request.json

    # Start the file processing in a separate thread
    thread = threading.Thread(target=process_files, args=(data,))
    thread.start()

    return jsonify({"message": "Processing started"})

@app.route("/stop_query", methods=["POST"])
def stop_query():
    """Stop the current query without clearing results."""
    global progress

    if progress.get("running", False):
        progress["stop_requested"] = True  # Signal to stop processing
        progress["status"] = "stopped"    # Update the status
        return jsonify({"message": "Query stopping..."}), 200
    else:
        return jsonify({"message": "No query is currently running."}), 400
    
@app.route("/download_all_files", methods=["GET"])
def download_all_files():
    """Create a ZIP archive dynamically and send it to the user."""
    global results

    bucket_name = "noaa-jpss"
    client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    zip_buffer = io.BytesIO() 

    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for result in results:
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



@app.route("/get_progress", methods=["GET"])
def get_progress():
    """Get the current progress and results."""
    return jsonify({"progress": progress, "results": results})


#static map
matplotlib.use('agg') 
# @app.route("/plot.png")
# def plot_map():
#     fig = create_map()
#     output = io.BytesIO()
#     FigureCanvas(fig).print_png(output)
#     return Response(output.getvalue(), mimetype="image/png")

# def create_map():
#     fig = plt.figure(figsize=(6, 4))
#     ax = fig.add_subplot(1, 1, 1, projection=ccrs.LambertConformal())
#     ax.set_extent([-179, -140, 50, 75], crs=ccrs.PlateCarree())
#     ax.add_feature(cfeature.LAND)
#     ax.add_feature(cfeature.OCEAN)
#     ax.add_feature(cfeature.COASTLINE)
#     ax.add_feature(cfeature.BORDERS, linestyle=":")
#     ax.add_feature(cfeature.LAKES, alpha=0.5)
#     ax.add_feature(cfeature.RIVERS)
#     return fig

@app.route("/grid_and_render", methods=["POST"])
def grid_and_render():
    """Grid data using files from the results list and return a map as a binary PNG."""
    try:
        global results
        bucket_name = "noaa-jpss"
        client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

        if not results:
            return jsonify({"error": "No files available in results for gridding"}), 400

        # Fetch file objects from S3 using results
        file_streams = []
        for result in results:
            file_key = result["file"]
            response = client_s3.get_object(Bucket=bucket_name, Key=file_key)
            file_stream = io.BytesIO(response["Body"].read())
            file_streams.append(file_stream)

        # Define geographic bounds and resolution
        lat_min, lat_max = 50, 75
        lon_min, lon_max = -179, -140
        resolution = 0.25

        # Call the gridding function
        plot_png = gridding.process_and_grid(
            file_streams, lat_min, lat_max, lon_min, lon_max, resolution
        )

        # Return the PNG image
        return Response(plot_png, mimetype="image/png")

    except Exception as e:
        print(f"Error during gridding: {e}")
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(debug=True)
