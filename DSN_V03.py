#----
version="DSN_python V03"
version_date="06/12/2025"
#----
#     Original FORTRAN written by A.D. Grauer
#     Converted to python and expanded by E.E. Falco
#     This program reads from an SQM or TESS output file
# Modus operandi:
#     python DSN_V03.py DataFile
#----
# IMPORTS
import warnings
warnings.filterwarnings('ignore')
#
import datetime
from datetime import date, time,  timedelta
from datetime import datetime as dt
import juliandate as jd
import pytz  # for time zones
import numpy as np
from numpy import arange
from numpy.polynomial import Polynomial as P
import pandas as pd
import os
import csv
import time
import sys
import re
import astropy.units as u
import astropy.coordinates as coord
from astropy.time import Time
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, Galactic
from astropy.coordinates import get_sun, get_moon
from astropy.io import fits
from scipy.optimize import curve_fit
import ephem
from fuzzywuzzy import fuzz, process
from github import Github
#
# INITIALIZATIONS
#
ihead=0
mag_zero=21.15 # Bará et al. 2019 zeropoint
JD_midnight = 0.7916667 # local midnight for each night in UTC, hours
JD_2AM = 0.875 # hours for 2AM in UTC
JD_4AM = 0.958333 # hours for 4AM in UTC
JD_3sep2017 = 2458000 # 3 sep 2017 JD
#moonlimit=-10
#MWlimit=70 
nentries=150000
nxy=5000
# factor to convert to nW/cm^2/sr from 21 msas
fnwcm2sr = 0.05746 # 0.063*10**((21-21.15)/2.5) to adjust to Bará scale
#
imoon=np.full(nentries,10)
isun=np.full(nentries,1)
ts=np.zeros(nentries)
sunalt=np.zeros(nentries)
#MWalt=np.zeros(nentries)
#
x=np.zeros(nxy)
y=np.zeros(nxy)
nstart=np.full(nxy,0)
nend=np.full(nxy,0)
night_count=np.full(nentries,0)
SQM=np.zeros(nentries)
chisquared=np.zeros(nentries)
Etempc=np.zeros(nentries)
Stempc=np.zeros(nentries)
volt=np.zeros(nentries)
freq=np.zeros(nentries)
moonalt=np.zeros(nentries)
# want the following set to True for pd columns w/o whines
pd.options.mode.copy_on_write = True
#     DSN SQM or TESS site Information
cols_sites = ['long','lat','el','sensor','ihead','dark',
              'bright','Site']
DSNsites_path='./'
if 'TESTING' in os.environ:
    if os.environ['TESTING']: 
        DSNsites_path=os.getenv('DSNdata') # for testing
        print("+++++++++++++++TESTING: ",DSNsites_path)
infile_sites=DSNsites_path+'DSNsites.csv'
frame_sites=pd.read_csv(infile_sites,header=None,skiprows=1,sep=',')
frame_sites.columns=cols_sites
#print(frame_sites)
frame_sites.index = np.arange(1, len(frame_sites) + 1)
# site data from DSNsites.csv
site_names=frame_sites.Site
#print("\t\tKnown sites\n","Site No.\t\t Name")
#print(site_names)
# Define functions, using astropy functions
#**************
#      Compute rise/set times and altitude above horizon
#**************new altsun
def altsun1(tlat,tlong,tele,utc):
    sun_time = Time(utc) #UTC time
    loc = EarthLocation.from_geodetic(tlong,tlat,tele)
    altaz = AltAz(obstime=sun_time, location=loc)
    alt_ang = get_sun(sun_time).transform_to(altaz).alt.degree
    return alt_ang
#**************new altmoon
def altmoon1(tlat,tlong,tele,utc):
    moon_time = Time(utc) #UTC time
    loc = EarthLocation.from_geodetic(tlong,tlat,tele)
    altaz = AltAz(obstime=moon_time, location=loc)
    alt_ang = get_moon(moon_time).transform_to(altaz).alt.degree
    return alt_ang
#**************moon phase with ephem
def moon_phase1(tlat,tlong,utc):
    moon=ephem.Moon()
    observer = ephem.Observer()
    observer.lat = tlat
    observer.long = tlong
    observer.date = utc
    moon.compute(observer)
    return moon.moon_phase
#***************new MW calc
# for a given lat,lon,utc return MW max elevation
# for a range of galactic lon, -180 to 180 in 12 steps
def altMW0(tlat,tlong,tele,utc):
    loc = EarthLocation.from_geodetic(tlong,tlat,tele)
    longs=np.linspace(-180,180,12)
    MW_time = Time(utc)
    alt_ang=np.max(Galactic(l=longs*u.deg, b=0*u.deg).transform_to(
                AltAz(location=loc, obstime=MW_time)).alt.value)
    return alt_ang
#***************** second version of altMW, 
# for a given lat,lon,utc return lon, MW elevations
# for a range of galactic lon, -180 to 180 in 12 steps
def altMW1(tlat,tlong,tele,utc):
    loc = EarthLocation.from_geodetic(tlong,tlat,tele)
    longs=np.linspace(-180,180,12)
    MW_time = Time(utc)
    alt_ang=Galactic(l=longs*u.deg, b=0*u.deg).transform_to(
                    AltAz(location=loc, 
                    obstime=MW_time)).alt.value
    return longs, alt_ang
#******************
# calculate galactic latitude of zenith at time utc
def z_MWlat0(tlat,tlong,tele,utc):
    loc = EarthLocation.from_geodetic(tlong,tlat,tele)
    obs_time = Time(utc, location=(tlong, tlat))
    z_lst=obs_time.sidereal_time('apparent').degree # 
    z_coo = SkyCoord(ra=z_lst*u.degree, dec=tlat*u.degree, frame='icrs')
    z_MWlat=z_coo.galactic.b.degree
    return np.abs(z_MWlat)
#******************
# calculate galactic latitude of zenith at times utc
def z_MWlat(tlat,tlong,tele,utc):
    loc = EarthLocation.from_geodetic(tlong,tlat,tele)
    obs_time = Time(utc, location=(tlong, tlat))
    z_lst=obs_time.sidereal_time('apparent').degree # 
    z_coo = SkyCoord(ra=z_lst*u.degree, dec=tlat*u.degree, frame='icrs')
    z_MWlat=z_coo.galactic.b.degree
    return np.abs(z_MWlat)
#********************polynomial fitting function for cloud detection
def mycurve_fit(x, y, ndata,degree):
    xxx=x-np.mean(x)
    y_poly=np.polyfit(xxx,y,degree)
    y_fit=np.poly1d(y_poly)
    y_dif=y_fit(xxx)-y
    chi2 = np.max([np.sum((y_dif)*(y_dif)),1.E-5])
    return chi2 
#***********************
def tloc_ut(frame_sensor):
    df=frame_sensor.copy()
# Arizona Timezone
    arizona_tz = pytz.timezone("America/Phoenix")
    df["Tloc"] = pd.to_datetime(df["Tloc"], format="%y%m%d%H%M")
    df["Tloc"] = df["Tloc"].dt.tz_localize(arizona_tz)
    df["UT"] = df["Tloc"].dt.tz_convert("UTC")
    ut = df["UT"].dt.strftime('%Y-%m-%dT%H:%M:%S Z')
    df["Tloc"]=df["Tloc"].dt.tz_localize(None)
    df["UT"]=df["UT"].dt.tz_localize(None)
    return ut,df
#***************
# lambda function center time on local midnight
jdlam=(lambda jd : jd if jd<12 else jd-24)
#**********************
#***************calculate cloud chisquared
def chicalc(JD,SQM,ndata):
# definitions
    icount=len(JD)
    hndata = int((ndata-1)/2)
    nstart1=np.full(icount,0)
    nend1=np.full(icount,0)
# find where local day changes
    jd_thr=6/24
    nstart1=[i+1 for i in range(1,icount-1) if (JD[i+1]-JD[i])>jd_thr]
    nstart1=np.insert(nstart1,0,0)
# set inight
    inight=len(nstart1)
    nend1=[nstart1[i]-1 for i in range(1,len(nstart1))]
    nend1=np.append(nend1,icount-1)
#
    endstart=np.sum(nend1+1-nstart1)-icount
    if endstart != 0:
        print("Night mismatch: ",endstart)
    print("Chicalc: No. of nights ",inight," endstart test ",endstart)
    chisquared = np.zeros(icount)
#
    for ii in range(inight):
        ns=nstart1[ii]
        ne=nend1[ii]
        n1=ns
        n2=n1+ndata+ndata
        n3=ne-ndata-ndata
# low end, fit hndata points instead of full ndata
        chisquared[n1:n2+1]= \
            [mycurve_fit(JD[nn:nn+hndata],SQM[nn:nn+hndata],hndata,2)#dark[nn]) 
                for nn in range(int(n1),int(n2)+1)]
# main, fit ndata points
        chisquared[n2+1:n3] = [mycurve_fit(JD[nn-hndata:nn+hndata],
            SQM[nn-hndata:nn+hndata],ndata,1)#dark[nn]) 
                for nn in range(int(n2)+1,int(n3))]
# high end, fit hndata points instead of full ndata
        chisquared[n3:ne+1]=[mycurve_fit(JD[nn-hndata:nn],
            SQM[nn-hndata:nn],hndata,2)#dark[nn]) 
                for nn in range(int(n3),int(ne)+1)]
    return np.around(chisquared,5)
##################################################################
#MAIN: 
#Ingest raw SQM or TESS files, generate standardized csv tables for
#analysis and visualization
##################################################################
if len(sys.argv) > 1:
    in_file= sys.argv[1]
else:
    print('Argument missing: SQM/TESS input file, try again.')
    quit()
print('Input file :',in_file)
# find the site number
site_dict = {idx: el for idx, el in enumerate(site_names.values)}

#remove the path
site_file = os.path.basename(in_file)
# find the first underscore, last "." and "DSN" in DSNnnn-X_SiteName
iunder=site_file.find('_')
idot=site_file.rfind('.')
idsn=site_file.find('DSN')
DSN_name=site_file[idsn:idsn+8]
#print(site_file[:iunder])
#print(site_dict)
matches = process.extract(site_file[:iunder], site_dict, limit=1)
site_number=matches[0][2]+1
iunder=site_names[site_number].rfind('_')+1
site_name=site_names[site_number][iunder:]
SorT=DSN_name[-1] # S or T
# for influx formatting
inf_measurement=DSN_name[:6]+SorT+"_"+site_name
print("*********",inf_measurement)
inf_file=inf_measurement+"_"+site_file[idsn+7:idot]

print("DSN name: ",DSN_name,"Site name: ",site_name," Number: ",site_number)
#
sensor_name = frame_sites.sensor.iloc[site_number-1].strip()
print("Sensor name ",sensor_name)
#
start_time=time.time()
tlong = frame_sites.long.iloc[site_number-1]
tlat = frame_sites.lat.iloc[site_number-1]
#  elevation in meters above sea level
tele = frame_sites.el.iloc[site_number-1]

# Check input file for comment lines
n_comments=0
FMT=""
if not in_file.endswith('.xlsx'):
    f=open(in_file,'r')
    while True:
        line = f.readline()
        if not line:
            print("EOF reached, no data, QUIT.")
            sys.exit(0)
        if line.startswith('#'):  # Check for a comment
            n_comments += 1
            continue  # Skip the line if it's a comment
        else:
            # find column separator
            if "," in line:
                sepcol=","
            else:
                sepcol=";"
            t_first=line.split(sepcol)[0]
            line=f.readline()
            t_secnd=line.split(sepcol)[0]
            if t_first.isalpha():
                continue
            if FMT=="": 
        # look for T in time, set FMT accordingly
                if "T" in t_first:
                    FMT="%Y-%m-%dT%H:%M:%S.%f"
                else:
                    FMT="%Y-%m-%d %H:%M:%S"
            # readout interval
            read_delta=(dt.strptime(t_secnd,FMT)-
                        dt.strptime(t_first,FMT)).total_seconds()
            
            read_delta /= 60.
            break
    print("Found ",n_comments," comment lines")
else:
    read_delta=10 # for Sugarloaf
#

if n_comments==0:
    ihead=1
else:
    ihead = n_comments
#  ndata is number of points used in cloud detection
# For 5 min spaced data
# ndata = 25 gives an hour on each side of a data point
# ndata = 19 gives 45 min on each side of a data point
# For 1 min spaced data
# ndata = 39  gives 17 min on each side of data point
#  Sugarloaf CNP Arizona has 10 min spacing
if read_delta == 5.:
    ndata=19
elif read_delta == 10:
    ndata=11
else:
    ndata=9
# open the file to open with pandas
i_file=open(in_file,'r')
# 2 sensor types
# for chisquared measurement
if sensor_name == 'SQM':
    frame_cols=['UT','Tloc','Etempc','volt','SQM','irec']
if sensor_name == 'SQM3': # HG format in Box
    frame_cols=['UT','Tloc','SQM','Etempc']
#        'Precip','SQM','Stempc','Battery','Dtempc']
#if site_number == 12: # Bonita unassigned
#        'Precip','SQM','Stempc','Battery','Dtempc']
if sensor_name == 'SQM2': # NOIRLab, Gilinsky
    frame_cols=['UT','Tloc','Etempc','counts','freq','SQM']
# UTC Date & Time, Local Date & Time, Temperature, Counts, Frequency, MSAS
# YYYY-MM-DDTHH:mm:ss.fff;YYYY-MM-DDTHH:mm:ss.fff;Celsius;number;Hz;mag/arcsec^2
if sensor_name == 'TESS':
    frame_cols=['UT','Tloc','tamb','tsky','SQM']
    use_cols=[0,1,2,3,5]

if 'JB' in site_name:
    head_skip=0 # special case of TESS data from John B
else:
    head_skip=4
#
# frame_sensor is a dataframe with the data from input file(s)
if sensor_name == 'SQM1': # .xlsx data
    if site_name == 'Sugarloaf':
        orig_cols = ['Tloc', 'Solar', 'Winds', 'Windd', 'Etempc', 'RH',
                 'Barom', 'Precip','SQM', 'Stempc', 'Battery', 'Dtempc']
    else:
        orig_cols = ['Tloc', 'Precip', 'SQM', 'Etempc', 'Solar','Winds',
                     'Windd','Stempc','RH','Barom', 'Battery', 'Dtempc']
    frame_sensor=pd.read_excel(in_file,header=None, skiprows=head_skip)
    frame_sensor.columns=orig_cols
    frame_sensor.drop(['Solar','Windd','RH','Barom','Precip','Stempc','Dtempc'], axis=1, inplace=True)
    UT,frame_sensor = tloc_ut(frame_sensor)
elif sensor_name == 'TESS':
    frame_sensor=pd.read_csv(in_file,header=None,skiprows=ihead,sep=sepcol,usecols=use_cols)
    frame_sensor.columns=frame_cols
#    print(frame_sensor.head(50))
    frame_sensor.rename(
        columns={"mag":"SQM","Time":"Tloc","tsky":"Stempc",
                 "tamb":"Etempc"},inplace=True)
else:
    frame_sensor=pd.read_csv(in_file,header=None,skiprows=ihead,sep=sepcol)
    len_cols=len(frame_sensor.columns)
    if sensor_name == 'SQM3': # G96,V06 format
        frame_cols=['UT','Tloc','SQM','Etempc','Stempc']
        drop_cols=list(range(4,5))+list(range(6,len(frame_sensor.columns)))
        frame_sensor.drop(columns=drop_cols,inplace=True)
        #        print(frame_cols)
    elif sensor_name == 'SQM4':
        frame_cols=['UT','Tloc','SQM','Stempc','Etempc'] # Etempc is RH here
    # relabel columns
    frame_sensor.columns=frame_cols

if read_delta < 1: # for MtLemmon G96
    read_delta=1
    
if read_delta == 1: # for normal TESS, JB special, MtLemmon G96
    df=frame_sensor
    frame_sensor = df[df.index % 5 == 0] 
    frame_sensor.reset_index(inplace=True,drop=True)
    ndata=19
print("Read interval: ",round(read_delta)," min. Points for chisquared: ",ndata)
#
# for TESS, period is 1 min, bring it down to 5 min
if sensor_name == 'TESS1':
    frame_sensor.rename(
        columns={"mag":"SQM","Time":"Tloc","tsky":"Stempc",
                "tamb":"Etempc"},inplace=True)
    lenJ = len(frame_sensor)
    local_time = [frame_sensor.Tloc.iloc[i] for i in range(lenJ)]
# Localize the datetime object to your local timezone
    local_time_aware = [local_time[i].tz_localize("America/Phoenix") for i in range(lenJ)]
# Convert the localized datetime object to UTC
    utc_time_John = [local_time_aware[i].tz_convert(None) for i in range(lenJ)]
    frame_sensor.insert(0, "UT", utc_time_John)
icount0=len(frame_sensor)
# drop duplicates, as in OR data
frame_sensor.drop_duplicates(inplace=True)
icount=len(frame_sensor)
print('Total number of data: ',icount,'dups dropped ',
      icount0-icount,' from ',in_file)
#
# correct UT for bad time shift
UTC=frame_sensor.UT
#
icount=len(frame_sensor)
nsite=np.full((icount),site_number)
#
JD_midnight_2=np.full(icount,JD_midnight) # default is offset 7h to UT
#
if (site_number>1): # for AZ
    df=frame_sensor[['UT','Tloc']]
#    print(frame_sensor.head())
#    df["UT"] = pd.to_datetime(df["UT"], format="%Y-%m-%d %H:%M:%S")
    df['UT'] = pd.to_datetime(df['UT'], utc=True)
    df['Tloc'] = pd.to_datetime(df['Tloc']).dt.tz_localize('America/Phoenix')
    df['Tloc_utc'] = df['Tloc'].dt.tz_convert('UTC')
    # Now subtraction is valid
    ut_tloc = (df['UT'] - df['Tloc_utc']) / pd.Timedelta(hours=1)
#    ut_tloc=(pd.to_datetime(df.UT)-pd.to_datetime(df.Tloc))/\
#            pd.Timedelta(hours=1)
    ut_tloc_bad=np.where(ut_tloc!=7)[0]
#    if (len(ut_tloc_bad)>0):
#        df.Tloc=pd.to_datetime(df.UT).dt.tz_localize('America/Phoenix')
#        df.Tloc=df.Tloc.dt.tz_convert(None)        
    frame_sensor.Tloc=df.Tloc
    print("Adjusted ",len(ut_tloc_bad)," UT values for AZ")
if (site_number==1): # for New Mexico
    df=frame_sensor[['UT','Tloc']]
    ut_tloc=(pd.to_datetime(df.UT)-pd.to_datetime(df.Tloc))/\
            pd.Timedelta(hours=1)
    ut_tloc_reg=np.where(ut_tloc==6)[0]
    JD_midnight_reg=np.around(JD_midnight-1./24.,6) # NM UT midnight for DST
    JD_midnight_2[ut_tloc_reg]=JD_midnight_reg
#    ut_tloc_bad=np.where(ut_tloc!=6)[0]
#    if (len(ut_tloc_bad)>0):
#        df.Tloc=pd.to_datetime(df.UT).dt.tz_localize('Etc/GMT-6')
#        df.Tloc=df.Tloc.dt.tz_convert(None)        
    frame_sensor.Tloc=df.Tloc
    print("Adjusted ",len(ut_tloc_reg)," UT values for NM")
#
frame_sensor['JD_mid']=JD_midnight_2 # add JD_midnight value as new column
UTC=frame_sensor.UT
Tloc=frame_sensor.Tloc
JD =pd.DatetimeIndex(frame_sensor['UT']).to_julian_date()
if not JD.is_monotonic_increasing:
    for i in range(len(JD)-1):
        i1=i+1
        if JD[i1]<JD[i]:
            print(i,JD[i],JD[i1],Tloc[i],Tloc[i1],frame_sensor.iloc[i-5:i+5])
    print('JD not monotonic, QUIT')
    quit()

# new altsun uses astropy sun routines
sunalt = altsun1(tlat,tlong,tele,list(UTC)) # calculates the whole vector of values

# Set the Sun flag to 0 when Sun below one of the angles below...
sun_dark = -18.
sun_8 = -8.0 # allow brighter sun (mainly SQM1)
sun_6 = -6.0 # "
sun_5 = -5.0 # "
sun_4 = -4.0 # "
sun_3 = -3.0 # "
isun = [0 if sunalt[i]<=sun_3 else 10 for i in range(icount)] # all data
dark = [1 if sunalt[i]<=sun_dark else 2 for i in range(icount)] # night
# sun_index contains all indices with sun below criterion above
#
sun_index=[i for i in range(icount) if isun[i]==0]
len_sun = len(sun_index)
df=frame_sensor.iloc[sun_index]
############################################
# DROP entries outside sun limit above
############################################
frame_sensor=df.reset_index(drop=True)
# icount: number of SQM data points filtered by sun limit above
icount=len(frame_sensor)
#
print('Number of entries after sun filter: ',icount)
if (icount == 0):
    print(f"No useful data in {in_file}, QUIT.")
    sys.exit(0)
#
#  Calculate JD and JDM
JD =pd.DatetimeIndex(frame_sensor['UT']).to_julian_date()
JD_mid=frame_sensor.JD_mid.values
JDM = [jdlam(np.around(np.modf(JD[i]-JD_mid[i])[0]*24,5)) 
       for i in range(icount)]
print('First and Last JD :',np.around(JD[0],5),np.around(JD[-1],5))
# reorder sunalt, dark for data filtered by sun limit
sunalt=[sunalt[ii] for ii in sun_index]
dark=[dark[ii] for ii in sun_index]
#
# Determine the number of nights = inight
# Determine the start and end points of each night for all Sun elevations
jd_thr=6/24.# threshold JD in day units
nst_thr=3*ndata # smallest allowed number of data in a night
nstart1=np.full(icount,0)
nend1=np.full(icount,0)
# JD jumps by >jd_thr from night to night
nstart1=[i+1 for i in range(1,icount-1) if (JD[i+1]-JD[i])>jd_thr]
nstart1=np.insert(nstart1,0,0) # always start at 0
nend1=[nstart1[i]-1 for i in range(1,len(nstart1))]
nend1=np.append(nend1,icount-1) # add the very last index
#
endstart=np.sum(nend1+1-nstart1)-icount
if endstart != 0:
    print("Night mismatch: ",endstart)
#
inight=len(nstart1) # number of nights to process
#####################################
# DROP nights with no. entries < nst_thr
#####################################
nsun=np.full(icount,0)
for i in range(inight):
    ijump=0
    if (nend1[i]-nstart1[i]<nst_thr):
#        print(i,nend1[i]-nstart1[i],nst_thr)
        ijump=10
    nsun[int(nstart1[i]):int(nend1[i]) + 1] = ijump
nst_index=[i for i in range(icount) if nsun[i]==0]
#####################################
# FILTERED nights
#####################################
print('Number of entries ',icount,' after filtering: ',len(nst_index))
if len(nst_index)==0:
    print("INSUFFICIENT No. of readings:")
    print(frame_sensor.head())
    quit()
icount=len(frame_sensor)
# cleanup sunalt, FINAL VERSION
SQM=np.array(frame_sensor.SQM.values)
nst_index=[i for i in range(icount) if nsun[i]==0 and SQM[i]>1.] # reset it
df=frame_sensor.iloc[nst_index]
frame_sensor=df.reset_index(drop=True)

# REALIGN sunalt,dark,JD
sunalt=[sunalt[ii] for ii in nst_index]
dark=[dark[ii] for ii in nst_index]
JD=[JD[ii] for ii in nst_index]
icount=len(sunalt)
# frame_sensor is now CLEAN
SQM=np.array(frame_sensor.SQM.values)
tloc=pd.DatetimeIndex(frame_sensor.Tloc)
locyr=np.array(tloc.year)
locmon=np.array(tloc.month)
locday=np.array(tloc.day)
# recreate start end post filtering
nstart1=np.full(icount,0)
nend1=np.full(icount,0)
# find where local day changes
nstart1=[i+1 for i in range(1,icount-1) if (JD[i+1]-JD[i])>jd_thr]
nstart1=np.insert(nstart1,0,0)
# reset inight now
inight=len(nstart1)
nend1=[nstart1[i]-1 for i in range(1,len(nstart1))]
nend1=np.append(nend1,icount-1)
#
endstart=np.sum(nend1+1-nstart1)-icount
if endstart != 0:
    print("Night mismatch: ",endstart)
#
run_time = time.time()-start_time
print("+++ RUN time after filtering (sec): ",np.around(run_time,2))

start_time=time.time()
#if (site_number==3 or site_number==5 or site_number ==15 ): 
# some SQM files use UTC-MST=6, wrong for AZ
#    df=frame_sensor.copy()
#    df = pd.to_datetime(df.Tloc)
#    df = df - pd.Timedelta(hours=1)
#    frame_sensor.Tloc=df # now Tloc (and the rest of the timestamp) is correct
#
UTC=frame_sensor.UT
#UTC_strip=[str(UTC[i]).strip().replace("T"," ") for i in range(len(UTC))]
#print("UTC_strip: ",UTC_strip[:5])
UTC_strip = [
    (s if '.' in s else s + '.000')
    for s in [str(UTC[i]).split('+')[0].replace(' ', 'T') for i in range(len(UTC))]
]
t = Time(UTC_strip, format='isot', scale='utc', location=(tlong, tlat))
#UTCzeros=UTC_strip[0][-4:]
#if UTCzeros == ".000":
#    UTC_strip=[UTC_strip[i][:-4] for i in range(icount)]
#t = Time(UTC_strip, scale='utc', location=(tlong, tlat))
LST=t.sidereal_time('apparent').hour # agrees with Al within < 1 sec

#
if sensor_name == 'TESS1' : # special case
    Stempc = frame_sensor.Stempc
    Etempc=frame_sensor.Etempc
else:
    Etempc=frame_sensor.Etempc
#if sensor_name == 'SQM' :
#    volt=frame_sensor.volt
#    irec=frame_sensor.irec
#if sensor_name == 'SQM1':
#    volt=frame_sensor.Battery
#    wind=frame_sensor.Winds
if sensor_name == 'SQM2':
    counts=frame_sensor.counts
if sensor_name == 'TESS' :
    Stempc = frame_sensor.Stempc
#
#     Cloud Detection
#     Fit segments of the SQM data to a straight line
#     ndata is number of points used in fit
#     for 5 min data spacing
#     ndata = 19 means cloud free for 45min on either side of 
#     point for 1.5 hr total
print("Number of points in cloud detection =",ndata)
run_time = time.time()-start_time
print("+++ RUN time just before cloud filter (sec): ",np.around(run_time,2))
start_time = time.time() # time cloud filter
#
hndata = int((ndata-1)/2)
# Deal with NO data, indicated by <=0 values
# NOW only SQM>1 are included, skip this
#SQM_zero=np.where(SQM<=0)[0]
#for ii in SQM_zero:
#    if ii<icount-1:
#        SQM[ii]=(SQM[ii-1]+SQM[ii+1])/2
#    else:
#        SQM[ii]=SQM[ii-1]
#
#print("*** Averaged ",len(SQM_zero)," SQM values")
###
#  Moon Elevation Calculation
# USE astropy moon routine, in altmoon1
UTC_list=list(UTC)
moonalt=altmoon1(tlat,tlong,tele,UTC_list)
run_time = time.time()-start_time
print("+++ RUN time after moonalt (sec): ",np.around(run_time,2))

start_time=time.time()
# calculate MW altitude after discrimination for brightness limits,
#  sun, moon, clouds
#MWalt = altMW(tlat,tlong,tele,UTC_list)
#run_time = time.time()-start_time
#print("+++ RUN time after MWalt (sec): ",np.around(run_time,2))
#start_time=time.time()
#
# Determine the start and end points of astronomical twilight
# for each night, look for change from <sun_dark to >sun_dark
ii=0
nstart=np.full(inight,0)
nend=np.full(inight,0)
for i in nstart1:
    i2=int(nend1[ii]+1)
    i = int(i)
    if sunalt[i]< sun_dark:
        i1=next((j for j in range(i,i2) if sunalt[j]>sun_dark),i2-1)
        i3=next((j for j in range(i1,i2) if sunalt[j]<=sun_dark),i2-1)
    else:
        i1=next((j for j in range(i,i2) if sunalt[j]<=sun_dark),i2-1)
        i3=next((j for j in range(i1,i2) if sunalt[j]>sun_dark),i2-1)
    nstart[ii]=i1
    nend[ii]=i3
    ii+=1
#
nstart=np.array(nstart)
nend=np.array(nend)
nsparse=np.min(np.min(nend-nstart))
night_sparse=np.where(nend-nstart==nsparse)[0][0]
print("*** Sparsest night is No. ",night_sparse," with ",nsparse," readings")
#
# night counter: night number for each entry in each night
night_count=[i for i in range(inight)
             for j in range(int(nstart1[i]), int(nend1[i]) + 1)]
# calculate chisquared, with interpolation at beg, end of night
start_time=time.time()
#
chisquared = np.zeros(icount)
#
for ii in range(inight):
    ns=nstart1[ii]
    ne=nend1[ii]
    n1=ns
    n2=n1+ndata+ndata
    n3=ne-ndata-ndata
# low end, fit hndata points instead of full ndata
    chisquared[int(n1):int(n2)+1]= \
        [mycurve_fit(JD[nn:nn+hndata],SQM[nn:nn+hndata],hndata,2)#dark[nn]) 
            for nn in range(int(n1),int(n2)+1)]
# main, fit ndata points
    chisquared[int(n2)+1:int(n3)] = [mycurve_fit(JD[nn-hndata:nn+hndata],
        SQM[nn-hndata:nn+hndata],ndata,1)#dark[nn]) 
            for nn in range(int(n2)+1,int(n3))]
# high end, fit hndata points instead of full ndata
    chisquared[int(n3):int(ne)+1]=[mycurve_fit(JD[nn-hndata:nn],
        SQM[nn-hndata:nn],hndata,2)#dark[nn]) 
                         for nn in range(int(n3),int(ne)+1)]
#
run_time = time.time()-start_time
print("+++ RUN time after cloud filter (sec): ",np.around(run_time,2))
start_time=time.time()
#  Open the output file for writing
# create output file name from input file
# for influxDB
INFpath='DSNdata/INFLUX/'
if 'TESTING' in os.environ:
    if os.environ['TESTING']: 
        influx_file='/tmp/INF-TESTING.csv' # for testing
        print("Real influx file: ",INFpath + inf_file + ".csv")
else:
    influx_file=INFpath + inf_file + ".csv"
# for DSNdata BOX, to transfer to Box
box_file="DSNdata/BOX/"+ site_file[:idot]+".csv"
print("InfluxDB file name ",influx_file)
# write influxdb file header
ofile=open(influx_file,'w')
_=ofile.write('#group,false,false,false,false,true,true\n')
_=ofile.write('#datatype,string,long,dateTime:RFC3339,double,string,string\n')
_=ofile.write('#default,,,,,,\n')
ofile.close()
# populate dataframe df
if sensor_name=="TESS":
    cols_df=['UTC','SQM','lum','chisquared','moonalt','LST','sunalt','Skytemp']
else:
    cols_df=['UTC','SQM','lum','chisquared','moonalt','LST','sunalt']
df=pd.DataFrame(columns=cols_df)
df.UTC=UTC_strip
df.UTC = [dt.strptime(str(df.UTC.iloc[i]).split('+')[0],
                      "%Y-%m-%dT%H:%M:%S.%f") for i in range(len(df))]
df["UTC"] = df.UTC.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
df.SQM=SQM
df.LST=np.array(LST)
# calculate radiance
lum=[fnwcm2sr*10**((mag_zero-SQM[ii])/2.5) for ii in range(icount)]
df.lum=lum
df.chisquared=chisquared
df.moonalt=moonalt
df.sunalt=sunalt
#
df.lum=np.around(df.lum,5)
df.chisquared=np.around(df.chisquared,5)
df.moonalt=np.around(df.moonalt,2)
df.LST=np.around(df.LST,5)
df.SQM=np.around(df.SQM,3)
df.sunalt=np.around(df.sunalt,3)
if sensor_name=="TESS":
    df.Skytemp=np.around(Stempc,2)
#print(df.head())
#
for second in ['SQM','lum','chisquared','moonalt']:
    df1=df[['UTC',second]]
    df1.insert(0,'','')
    df1.insert(0,'','',allow_duplicates=True)
    df1.insert(2,'table','',allow_duplicates=True)
    df1.rename(columns={'UTC':'_time'},inplace=True)
    df1.rename(columns={'UTC':'_time'},inplace=True)
    df1.rename(columns={second:'_value'},inplace=True)
    df1.insert(5,'_field','',allow_duplicates=True)
    df1.insert(6,'_measurement','',allow_duplicates=True)
    df1['_field']=second
    df1['_measurement']=inf_measurement
#
#   write header only for the first loop, when second=='SQM'
    df1.to_csv(influx_file,mode='a', header=(second=='SQM'),index=False)
print(version," ",version_date," Wrote ",4*len(df1)," entries to ",influx_file)
#print(df.head())
#
# Save the data to an archive file for Box.
if os.path.exists("DSNdata/BOX/"):
    df.to_csv(box_file,mode='w',header=cols_df,index=False)
    print(version," ",version_date," Wrote ",len(df)," entries to ",
          box_file)
else:
    min_value = df['SQM'].min()
# Find the index of the minimum value in SQM
    min_index = df['SQM'].idxmin()
    print(" SQM min ",min_value)
    print(df.iloc[min_index])
    df.to_csv("/tmp/TESTING.csv",mode='w',header=cols_df,index=False)
    print(version," ",version_date," Wrote ",len(df)," entries to ",
          "/tmp/TESTING.csv")
# THE END
