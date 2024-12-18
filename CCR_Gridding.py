import xarray as xr
import netCDF4
import scipy.interpolate
import timeit
from datetime import datetime, timedelta
import numpy as np
from numpy import genfromtxt
import glob
import pandas as pd
import matplotlib.pyplot as plt
import cartopy.crs as ccrs



def createGrid():
    nx = 720
    ny = 360
    nx_dim = 720j
    ny_dim = 360j

    # Coverage for the global grid.
    regionCoverage = [-179.9999999749438 , -89.9999999874719 , 179.9999999749438 , 89.9999999874719]
    Y, X = np.mgrid[regionCoverage[3]:regionCoverage[1]:ny_dim, regionCoverage[0]:regionCoverage[2]:nx_dim]
    xrout_dims =  (X.shape[0],X.shape[1], 2)

    return Y, X, xrout_dims

def restructurePoints(lats, lons):
    length = np.shape(lats)[0]
    points = np.zeros((length, 2))
    for i in range(length):
        points[i, 0] = lons[i]
        points[i, 1] = lats[i]
    return points

def generateMask(points, X, Y, threshold=1):
    mask = np.zeros((np.shape(X)))
    for point in points:
        lon = point[0]
        lat = point[1]
        distance = np.sqrt(np.power(X - lon, 2) + np.power(Y - lat, 2))

        mask[np.where(distance <= threshold)] = 1
    return mask

def horizontallyInter(points, variable, X, Y, mask):
    gridOut = scipy.interpolate.griddata(points, variable, (X, Y), method='nearest')
    gridOut[mask == 0] = np.nan
    return gridOut

def gridValues(xrout_dims, var, var_name, points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a):
    if var_name == 'Times':
        var=var/1e9

    gridded_vals = np.full(xrout_dims, fill_value=np.nan)

    if len(var[descend_flag]) > 0:
        gridded_vals[:,:,0] = horizontallyInter(points_d, var[descend_flag], X, Y, mask_d)


    if len(var[ascend_flag]) > 0:
        gridded_vals[:,:,1] = horizontallyInter(points_a, var[ascend_flag], X, Y, mask_a)

    dict_item = { var_name : (["x", "y", "ascend_descend"], gridded_vals) }

    return dict_item

def gridValuesRad(xrout_dims, var, var_name, points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a):

    xrout_dims_rad = (360, 720, 2, 130)
    gridded_vals = np.full(xrout_dims_rad, fill_value=np.nan)

    if len(var[descend_flag]) > 0:
        gridded_vals[:,:,0,:] = horizontallyInter(points_d, var[descend_flag], X, Y, mask_d)


    if len(var[ascend_flag]) > 0:
        gridded_vals[:,:,1,:] = horizontallyInter(points_a, var[ascend_flag], X, Y, mask_a)

    dict_item = { var_name : (["x", "y", "ascend_descend", "freq"], gridded_vals) }

    return dict_item

def generateGlobalAtrrs(search_day):
    # Global attributes for netCDF file
    date_created=datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    time_coverage=search_day[0:4]+'-'+search_day[4:6]+'-'+search_day[6:8]
    time_coverage_start=time_coverage+"T00:00:00Z"
    time_coverage_end=time_coverage+"T23:59:59Z"

    global_attrs = {
    'description' : "Ozone Channel Radiances Gridded from NUCAPS CCR v3r0 from NOAA-20",
    'Conventions' : "CF-1.5",
    'Metadata_Conventions' : "CF-1.5, Unidata Datasset Discovery v1.0",
    'institution' : "Science and Technology Corp.",
    'creator_name' : "Philip Casey",
    'creator_email' : "pcasey@stcnet.com",
    'platform_name' : "J01",
    'date_created' : date_created,
    'time_coverage_start' : time_coverage_start,
    'time_coverage_end' : time_coverage_end
    }

    return global_attrs

def generateEncodingAttrs(var_names):
    dict={}
    for var_name in var_names:
        dict.update( { var_name : {"zlib": True, "complevel": 9} })

    return dict

def MERRA2Time(times,year,month,day):
    z0, z1, z2, z3, z4, z5, z6, z7 = datetime(year, month, day, 0, 00), datetime(year, month, day, 3, 00), datetime(year, month, day, 6, 00), datetime(year, month, day, 9, 00), datetime(year, month, day, 12, 00), datetime(year, month, day, 15, 00), datetime(year, month, day, 18, 00), datetime(year, month, day, 21, 00)
    test_date_list = [z0, z1, z2, z3, z4, z5, z6, z7]
    merratime = []

    for i in times:
        if np.isnan(i) == True:
            merratime.append(np.nan)
        else:
            test_date = datetime.utcfromtimestamp(i)
            res = min(test_date_list, key=lambda sub: abs(sub - test_date))
            
            if res == z0:
                merratime.append(0)
            if res == z1:
                merratime.append(1)
            if res == z2:
                merratime.append(2)
            if res == z3:
                merratime.append(3)
            if res == z4:
                merratime.append(4)
            if res == z5:
                merratime.append(5)
            if res == z6:
                merratime.append(6)
            if res == z7:
                merratime.append(7)
    
    return merratime

def generatePlot(ds, var_name, search_day):
    vmin = ds[var_name].cbar_range[0]
    vmax = ds[var_name].cbar_range[1]
    cmap = ds[var_name].cmap

    time_coverage=search_day[0:4]+'-'+search_day[4:6]+'-'+search_day[6:8]

    subplot_kws=dict(projection=ccrs.PlateCarree(), transform=ccrs.PlateCarree())
    cbar_kwargs={"extend": "both", "orientation" : "vertical", "shrink" : .75, "cmap" : cmap}

    p = ds[var_name].plot(x="lon", y="lat", row="ascend_descend", figsize=[20,20], subplot_kws=subplot_kws, cbar_kwargs=cbar_kwargs, vmin=vmin, vmax=vmax)

    for i, ax in enumerate(np.flip(p.axes.flat)):
        ax.set_extent([-170, -20, 0, 70])
        ax.coastlines('50m')
        if i == 0:
            ax.set_title(time_coverage + " (ascending)")
        else:
            ax.set_title(time_coverage + " (descending)")

    plt.savefig(plotdir + search_day + '_' + var_name + '.png')
    plt.close()


#### Dates chosen for study period 2022-2023
# dates = pd.date_range(start="2022-10-01",end="2023-09-30").strftime("%Y/%m/%d")
# index = np.arange(0,365,4)

# for i in index:
#     print(dates[i])
days = (30,32)
# days = (2,6,10,14,18,22,26,30)
months = (11,13)
year = (2022)
for month in months:
    for day in days:   
        ddir = '/mnt/nucaps-s3/philip/RadianceNUCAPS/2022-2023/2022/' + str(month).zfill(2) + '/' + str(day).zfill(2) + '/'
        file_list = glob.glob(ddir+'*.nc')

        O3Chan = genfromtxt('/home/philip/ML-Trace-Gases/Ozone/Ozone_Temp_Channels.csv', delimiter=',',encoding="utf8")
        O3Chan= np.int_(O3Chan[:,0])

        Ascend_Decend = np.empty(0)
        Latitude = np.empty((0))
        Longitude = np.empty((0))
        Quality_Flag = np.empty((0))
        CrIS_Radiances = np.empty((0,130))
        View_Angle = np.empty((0))
        Satellite_Height = np.empty((0))
        Solar_Zenith = np.empty((0))
        Time = np.empty((0))
        MERRATime = np.empty((0))

        for file in file_list:
            nc = xr.open_dataset(file, decode_times=False)
            # nc = xr.open_dataset(file, decode_times=False)
            # lats = np.append(lats, npzfile['lat'])
            # lons = np.append(lons, npzfile['lon'])
            # ascend = np.append(ascend, npzfile['ascend'])
            Ascend_Decend =  np.append( Ascend_Decend, np.array(nc.Ascending_Descending, copy = True))
            Latitude = np.append( Latitude, np.array(nc.CrIS_Latitude, copy=True))
            Longitude = np.append(Longitude, np.array(nc.CrIS_Longitude, copy=True))

            Quality_Flag = np.append( Quality_Flag,nc.Quality_Flag.values)
            CrIS_Radiances = np.append(CrIS_Radiances, np.array(nc.CrIS_Radiances[:,O3Chan], copy=True), axis=0)

            View_Angle = np.append( View_Angle, nc.CrIS_View_Angle.values)
            Satellite_Height = np.append( Satellite_Height, nc.Satellite_Height.values)
            Solar_Zenith = np.append( Solar_Zenith, nc.Solar_Zenith.values)
            Time = np.append(Time, nc.Time.values)

        MERRATime = np.append(MERRATime, np.asarray(MERRA2Time((Time/1e3),year,month,day)))
        freqnc = xr.open_dataset(file_list[0], decode_times=False)
        CrIS_Frequencies = np.empty(0)
        CrIS_Frequencies  = np.append( CrIS_Frequencies,freqnc.CrIS_Frequencies[O3Chan].values)


        print('Gridding.py: Done combining files!')

        # -----------------------------------
        # Gridding
        #------------------------------------
        start = timeit.default_timer()

        Y, X, xrout_dims = createGrid()

        # Decending = 1, Ascending = 0
        ascend_flag = (Ascend_Decend==0)
        descend_flag = (Ascend_Decend==1)

        points_d = restructurePoints(Latitude[descend_flag], Longitude[descend_flag])
        points_a = restructurePoints(Latitude[ascend_flag], Longitude[ascend_flag])

        print("Gridding.py: Done making grids!")
        #2/7/23 ~ 17 min 



        # This takes ~ 32 mins/day
        mask_d = generateMask(points_d, X, Y, threshold=1.0)
        mask_a = generateMask(points_a, X, Y, threshold=1.0)

        print("Gridding.py: Done making masks!")

        data_vars = {}
        dict_item = gridValues(xrout_dims, Quality_Flag, 'Quality_Flag', points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a)
        data_vars.update(dict_item)
        dict_item = gridValuesRad(xrout_dims, CrIS_Radiances, 'CrIS_Radiances', points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a)
        data_vars.update(dict_item)
        dict_item = gridValues(xrout_dims, View_Angle, 'View_Angle', points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a)
        data_vars.update(dict_item)
        dict_item = gridValues(xrout_dims, Satellite_Height, 'Satellite_Height', points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a)
        data_vars.update(dict_item)
        dict_item = gridValues(xrout_dims, Solar_Zenith, 'Solar_Zenith', points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a)
        data_vars.update(dict_item)
        dict_item = gridValues(xrout_dims, Time, 'Time', points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a)
        data_vars.update(dict_item)
        dict_item = gridValues(xrout_dims, MERRATime, 'MERRA-2_Time', points_d, points_a, descend_flag, ascend_flag, mask_d, mask_a)
        data_vars.update(dict_item)

        print("Gridding.py: Done gridding variables!")


        # Global attributes for netCDF file
        # global_attrs = generateGlobalAtrrs(search_day)


        ds = xr.Dataset(
            data_vars=data_vars,

            coords=dict(
                lon=(["x", "y"], X),
                lat=(["x", "y"], Y),
                ascend_descend=[0, 1],
                freq = CrIS_Frequencies
            ),
            attrs=dict(description="Radiances"),
        )

        ds.to_netcdf('/mnt/nucaps-s3/philip/RadianceNUCAPS/2022-2023/'+'Ozone_CCR_Temp_Gridded_'+ str(year) + str(month).zfill(2)  + str(day).zfill(2) + '.nc', format='netCDF4')
        print("Done with day", day)