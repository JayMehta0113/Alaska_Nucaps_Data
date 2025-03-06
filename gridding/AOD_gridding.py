    
# new way with sending just points to leaflet frontend
import xarray as xr
import numpy as np
from rasterio.transform import from_origin
from rasterio.io import MemoryFile
import matplotlib.pyplot as plt
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

    aot = data['aot1'].isel(time=0).values  

    lat = data['latitude'].values
    lon = data['longitude'].values

    aot_flipped = np.flipud(aot)  #raster shows up flipped (north/south), this flips it back to normal

    """
    defining acceptable ranges based on high and low values in datase.
    this removes negative values with np.clip(). According to documentation: 
    (https://noaa-cdr-aerosol-optical-thickness-pds.s3.amazonaws.com/index.html#documentation/), this is okay for single
    day retrevals, however, in long term statistics, make sure to include negative values.
    """                
    aot_min, aot_max = 0, 0.5  
    aot_flipped = np.clip(aot_flipped, 0, 5)

    print(f"min aot: {np.nanmin(aot_flipped)}, max: {np.nanmax(aot_flipped)}")
    print(f"percent of points over 0.5: {(np.sum(aot_flipped>0.5)/np.size(aot_flipped))*100}")

    #creating the color map
    colormap = plt.colormaps.get_cmap("viridis")  
    rgb = colormap(aot_flipped)[:, :, :3]  
    rgb = (rgb * 255).astype(np.uint8).transpose(2, 0, 1) 

    #setting pixel size for gridded points
    pixel_width = (lon.max() - lon.min()) / aot.shape[1]
    pixel_height = (lat.max() - lat.min()) / aot.shape[0]
    transform = from_origin(lon.min(), lat.max(), pixel_width, -pixel_height)  

    #creating tif file, this will be overlayed on leaflet map
    tif_buffer = io.BytesIO()
    with MemoryFile(tif_buffer) as memfile:
        with memfile.open(
            driver="GTiff",
            height=aot.shape[0], width=aot.shape[1],
            count=3,  # RGB bands
            dtype=np.uint8,
            crs="EPSG:4326",
            transform=transform,
        ) as data_raster:
            data_raster.write(rgb)
            print('data written to raster')

        memfile.seek(0)
        tif_bytes = memfile.read()
        tif_buffer.write(tif_bytes)


    #Reset buffer position before sending
    tif_buffer.seek(0)
    buffer_size = len(tif_buffer.getvalue())
    
    if buffer_size == 0:
        print("Error: TIFF buffer is empty!")
    return tif_buffer