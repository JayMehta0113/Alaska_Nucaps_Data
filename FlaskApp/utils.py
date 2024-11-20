import xarray as xr
import boto3
from botocore.config import Config
import io
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure



def open_s3_dataset(bucket, key, client_s3):
    response = client_s3.get_object(Bucket=bucket, Key=key)
    data = response["Body"].read()
    data_io = io.BytesIO(data)
    return xr.open_dataset(data_io, engine="h5netcdf", chunks={}, decode_times=False)

def filter_data(dataset, lat_min, lat_max, long_min, long_max):
    # Compute boolean masks explicitly
    lat_mask = ((dataset["CrIS_Latitude"] >= lat_min) & (dataset["CrIS_Latitude"] <= lat_max)).compute()
    long_mask = ((dataset["CrIS_Longitude"] >= long_min) & (dataset["CrIS_Longitude"] <= long_max)).compute()

    # Combine the computed masks
    combined_mask = lat_mask & long_mask

    # Apply the mask to the dataset
    filtered_data = dataset.where(combined_mask, drop=True)

    # Check if filtered data has valid entries
    if filtered_data["CrIS_Latitude"].size > 0:
        return (
            filtered_data,
            float(filtered_data["CrIS_Latitude"].min()),
            float(filtered_data["CrIS_Latitude"].max()),
            float(filtered_data["CrIS_Longitude"].min()),
            float(filtered_data["CrIS_Longitude"].max()),
        )
    return None, None, None, None, None


def list_all_files(bucket_name, prefix, client_s3):
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

def create_map():
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.LambertConformal())
    ax.set_extent([-175, -50, 20, 75], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.OCEAN)
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.BORDERS, linestyle=":")
    ax.add_feature(cfeature.LAKES, alpha=0.5)
    ax.add_feature(cfeature.RIVERS)
    return fig

def plot_map():
    fig = create_map()
    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    return Response(output.getvalue(), mimetype="image/png")