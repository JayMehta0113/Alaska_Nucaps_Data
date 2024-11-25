import numpy as np
import xarray as xr
from scipy.interpolate import griddata
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from io import BytesIO
import boto3
from botocore.config import Config
from botocore import UNSIGNED


def create_grid(lat_min, lat_max, lon_min, lon_max, resolution=0.25):
    grid_lat, grid_lon = np.mgrid[
        lat_min:lat_max:resolution, lon_min:lon_max:resolution
    ]
    return grid_lat, grid_lon


def grid_data(lats, lons, values, grid_lat, grid_lon, method="linear"):
    grid_values = griddata(
        (lons, lats), values, (grid_lon, grid_lat), method=method
    )
    return grid_values


def process_file(file_obj, ozone_channel_indices):
    try:
        with xr.open_dataset(file_obj, decode_times=False) as nc:
            # Extract variables
            lats = nc["CrIS_Latitude"].values
            lons = nc["CrIS_Longitude"].values
            radiances = nc["CrIS_Radiances"][:, ozone_channel_indices].values
            quality_flag = nc["Quality_Flag"].values

            # Filter valid data
            valid_indices = np.where(quality_flag >= 0)[0]  # Non-negative quality flag
            if len(valid_indices) == 0:
                return None, None, None

            return (
                lats[valid_indices],
                lons[valid_indices],
                radiances[valid_indices, :].mean(axis=1),  # Average radiances across ozone channels
            )
    except Exception as e:
        print(f"Error processing file: {e}")
        return None, None, None


def create_map(grid_lon, grid_lat, gridded_values):
    """Create a map with gridded radiance data."""
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

    # Plot the gridded radiance data
    radiance_plot = ax.pcolormesh(
        grid_lon, grid_lat, gridded_values, 
        transform=ccrs.PlateCarree(), cmap="viridis", shading="auto"
    )

    # Add colorbar
    cbar = plt.colorbar(radiance_plot, orientation="vertical", pad=0.05)
    cbar.set_label("Radiance (Average of Ozone Channels)")

    plt.title("Gridded CrIS Radiance Data")

    # Save to a binary buffer
    output = BytesIO()
    plt.savefig(output, format="png")
    plt.close(fig)
    output.seek(0)
    return output


def process_and_grid(file_objects, lat_min, lat_max, lon_min, lon_max, resolution=0.25):
    # Define the ozone absorption band (~990–1080 cm⁻¹)
    ozone_band_min = 990
    ozone_band_max = 1080

    # Process the first file to determine ozone channel indices
    with xr.open_dataset(file_objects[0], decode_times=False) as nc:
        frequencies = nc["CrIS_Frequencies"].values
        ozone_channel_indices = np.where(
            (frequencies >= ozone_band_min) & (frequencies <= ozone_band_max)
        )[0]

    # Create the latitude-longitude grid
    grid_lat, grid_lon = create_grid(lat_min, lat_max, lon_min, lon_max, resolution)

    # Initialize lists to collect data
    all_lats, all_lons, all_values = [], [], []

    # Process each file
    for file_obj in file_objects:
        lats, lons, values = process_file(file_obj, ozone_channel_indices)
        if lats is not None:
            all_lats.extend(lats)
            all_lons.extend(lons)
            all_values.extend(values)

    # Grid the data
    gridded_values = grid_data(
        np.array(all_lats), np.array(all_lons), np.array(all_values), grid_lat, grid_lon
    )

    # Create and return the map as a binary PNG
    return create_map(grid_lon, grid_lat, gridded_values)


def process_and_grid_from_s3(bucket_name, prefix, lat_min, lat_max, lon_min, lon_max, resolution=0.25):
    """Fetch files from S3, process, grid data, and return the map."""
    client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    response = client_s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    if "Contents" not in response:
        raise FileNotFoundError("No files found in the specified bucket and prefix.")

    # Fetch files from S3
    file_objects = []
    for obj in response["Contents"]:
        file_key = obj["Key"]
        print(f"Fetching file: {file_key}")
        file_response = client_s3.get_object(Bucket=bucket_name, Key=file_key)
        file_buffer = BytesIO(file_response["Body"].read())
        file_objects.append(file_buffer)

    # Grid and process data
    return process_and_grid(file_objects, lat_min, lat_max, lon_min, lon_max, resolution)
