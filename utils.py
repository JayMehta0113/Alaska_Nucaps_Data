import xarray as xr
import boto3
from botocore.config import Config
import io
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure



# def open_s3_dataset(bucket, key, client_s3):
#     response = client_s3.get_object(Bucket=bucket, Key=key)
#     data = response["Body"].read()
#     data_io = io.BytesIO(data)
#     return xr.open_dataset(data_io, engine="h5netcdf", chunks={}, decode_times=False)

# def filter_data(dataset, lat_min, lat_max, long_min, long_max):
#     # Compute boolean masks explicitly
#     lat_mask = ((dataset["CrIS_Latitude"] >= lat_min) & (dataset["CrIS_Latitude"] <= lat_max)).compute()
#     long_mask = ((dataset["CrIS_Longitude"] >= long_min) & (dataset["CrIS_Longitude"] <= long_max)).compute()

#     # Combine the computed masks
#     combined_mask = lat_mask & long_mask

#     # Apply the mask to the dataset
#     filtered_data = dataset.where(combined_mask, drop=True)

#     # Check if filtered data has valid entries
#     if filtered_data["CrIS_Latitude"].size > 0:
#         return (
#             filtered_data,
#             float(filtered_data["CrIS_Latitude"].min()),
#             float(filtered_data["CrIS_Latitude"].max()),
#             float(filtered_data["CrIS_Longitude"].min()),
#             float(filtered_data["CrIS_Longitude"].max()),
#         )
#     return None, None, None, None, None


# def list_all_files(bucket_name, prefix, client_s3):
#     file_keys = []
#     continuation_token = None
#     while True:
#         if continuation_token:
#             response = client_s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=continuation_token)
#         else:
#             response = client_s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
#         file_keys.extend([obj["Key"] for obj in response.get("Contents", [])])
#         if response.get("IsTruncated"):
#             continuation_token = response["NextContinuationToken"]
#         else:
#             break
#     return file_keys

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

# def plot_map():
#     fig = create_map()
#     plt.show()
#     # output = io.BytesIO()
#     # FigureCanvas(fig).print_png(output)
#     # return Response(output.getvalue(), mimetype="image/png")

# plot_map()

import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

def create_grid(lat_min, lat_max, lon_min, lon_max, resolution=0.25):
    """Create a latitude-longitude grid."""
    grid_lat, grid_lon = np.mgrid[
        lat_min:lat_max:resolution, lon_min:lon_max:resolution
    ]
    return grid_lat, grid_lon

def create_map(grid_lon, grid_lat):
    """Create a static map with an empty color bar."""
    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.LambertConformal())
    ax.set_extent([-179, -140, 50, 75], crs=ccrs.PlateCarree())

    # Add map features
    ax.add_feature(cfeature.LAND, edgecolor="black", alpha=0.3)
    ax.add_feature(cfeature.OCEAN, alpha=0.5)
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.BORDERS, linestyle=":")
    ax.add_feature(cfeature.LAKES, alpha=0.5)
    ax.add_feature(cfeature.RIVERS)

    # Add title
    plt.title("Gridded CrIS Radiance Data")

    plt.show()

def generate_static_map():
    """Generate a static map with an empty color bar."""
    # Define grid bounds
    lat_min, lat_max = 50, 75
    lon_min, lon_max = -179, -140
    resolution = 0.25

    # Create the latitude-longitude grid
    grid_lat, grid_lon = create_grid(lat_min, lat_max, lon_min, lon_max, resolution)

    # Create the map
    create_map(grid_lon, grid_lat)

generate_static_map()
