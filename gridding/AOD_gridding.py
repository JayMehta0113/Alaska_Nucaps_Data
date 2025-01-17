import xarray as xr
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np
import io
import boto3
from botocore.config import Config
from botocore import UNSIGNED

def grid_aresol_data(file_key):

    file_key = ''.join(file_key)

    print("made it to AOD file")

    # Load the NetCDF file
    bucket_name = 'noaa-cdr-aerosol-optical-thickness-pds'
    client_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    aresol_data_file = client_s3.get_object(Bucket=bucket_name, Key=file_key)
    file_stream = io.BytesIO(aresol_data_file["Body"].read())
    
    data = xr.open_dataset(file_stream)

    print("opened the file from s3 bucket")

    # Extract aerosol optical depth (AOT) data
    aot = data['aot1'].isel(time=0)  
    lat = data['latitude']
    lon = data['longitude']

    # Check for missing data
    total_points = np.prod(aot.shape)
    missing_points = np.isnan(aot).sum().item()
    missing_percentage = (missing_points / total_points) * 100
    print(f"Total data points: {total_points}")
    print(f"Missing data points: {missing_points} ({missing_percentage:.2f}% missing)")

    # Plot the data on a world map
    fig = plt.figure(figsize=(14, 8))
    ax = plt.axes(projection=ccrs.PlateCarree())

    # Add map features (drawn first)
    ax.coastlines(resolution='50m', color='black', linewidth=1)
    ax.add_feature(cfeature.BORDERS, linestyle=':', linewidth=0.5)
    ax.add_feature(cfeature.LAND, edgecolor='black', facecolor='lightgray')
    ax.add_feature(cfeature.OCEAN, edgecolor='none', facecolor='lightblue')

    # Plot AOT data 
    aot_plot = plt.pcolormesh(lon, lat, aot, cmap='viridis', shading='auto', transform=ccrs.PlateCarree())

    # Add colorbar and labels
    cbar = plt.colorbar(aot_plot, orientation='vertical', pad=0.05)
    cbar.set_label('Aerosol Optical Thickness (AOT)')
    plt.title('Global Aerosol Optical Thickness (AOT)')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')

    #return the plot to server
    output = io.BytesIO()
    plt.savefig(output, format="png")
    plt.close(fig)
    output.seek(0)
    return output
    
