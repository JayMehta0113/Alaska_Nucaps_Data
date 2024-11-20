from flask import Flask, request, render_template, jsonify, Response
import boto3
from botocore.config import Config
from botocore import UNSIGNED
import xarray as xr
import io
import threading
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import matplotlib

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
    
    # Use fixed latitude and longitude bounds for now
    lat_min, lat_max = 51, 71
    long_min, long_max = -175, -141

    client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    file_keys = list_all_files(bucket_name, prefix, client_s3)

    progress["total_files"] = len(file_keys)
    progress["files_processed"] = 0

    for key in file_keys:
        dataset = open_s3_dataset(bucket_name, key, client_s3)
        filtered = filter_data(dataset, lat_min, lat_max, long_min, long_max)
        if filtered:
            results.append({"file": key, **filtered})
        progress["files_processed"] += 1

@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")

@app.route("/start_query", methods=["POST"])
def start_query():
    """Start processing files."""
    data = request.json

    # Start the file processing in a separate thread
    thread = threading.Thread(target=process_files, args=(data,))
    thread.start()

    return jsonify({"message": "Processing started"})

@app.route("/get_progress", methods=["GET"])
def get_progress():
    """Get the current progress and results."""
    return jsonify({"progress": progress, "results": results})

matplotlib.use('agg')
#static map
@app.route("/plot.png")
def plot_map():
    fig = create_map()
    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    return Response(output.getvalue(), mimetype="image/png")

def create_map():
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.LambertConformal())
    ax.set_extent([-179, -140, 50, 75], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.OCEAN)
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.BORDERS, linestyle=":")
    ax.add_feature(cfeature.LAKES, alpha=0.5)
    ax.add_feature(cfeature.RIVERS)
    return fig

if __name__ == "__main__":
    app.run(debug=True)
