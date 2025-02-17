import xarray as xr #
import io


def list_all_files(bucket_name, prefix, client_s3):
    """List all files in S3 bucket."""
    file_keys = []
    continuation_token = None
    while True:
        if continuation_token:
            #print(f"fetching next page with continuation token: {continuation_token}") #debug
            response = client_s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=continuation_token)
        else:
            #print(f"fetching first page with prefix: {prefix}") #debug
            response = client_s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        
        #debug
        # print(f"response: {response}")

        file_keys.extend([obj["Key"] for obj in response.get("Contents", [])])
        if response.get("IsTruncated"):
            continuation_token = response["NextContinuationToken"]
            #print("response is truncated, fetching next")
        else:
            #print("no more pages to fetch")
            break
    return file_keys

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