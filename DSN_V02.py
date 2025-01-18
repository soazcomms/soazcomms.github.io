#----
#     DSN_v02
#     01/17/2025
#
#     Original FORTRAN written by A.D. Grauer
#     Converted to python and expanded by E.E. Falco
#     This program reads from an SQM output file
#     Number of header lines: 38 or 37 or 35
#     Unihedron SQM or TESS

# COMMENTS FROM ORIGINAL FORTRAN VERSION:

#     Version February 10, 2020 corrects the sign of temperature
#     Works for the unbinned Unihedron format
#     Original FORTRAN was compiled with
#     gfortran Reduce_SQM4_13.f -o Reduce_SQM4_13
# COMMENTS ON python version:
#     python DSN_VXX.py DataFile
#----
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
# Array, constant Initializations
#
ihead=0
mag_ref=21.15 # Bará et al. 2019
JD_midnight = 0.7916667 # local midnight for each night in UTC, hours
JD_2AM = 0.875 # hours for 2AM in UTC
JD_4AM = 0.958333 # hours for 4AM in UTC
JD_3sep2017 = 2458000 # 3 sep 2017 JD
chisqlimit=0.009
moonlimit=-10
MWlimit=70 
nentries=150000
nxy=5000
# factor to convert to nW/cm^2/sr from 21 msas
fnwcm2sr = 0.05746 # 0.063*10**((21-21.15)/2.5) to adjust to Bará scale
#
SQM_dir='/Users/Bun/Desktop/DarkSkies/DS-SOAZ/SOFTWARE/SQMruns/'
imoon=np.full(nentries,10)
isun=np.full(nentries,1)
ts=np.zeros(nentries)
sunalt=np.zeros(nentries)
#MWalt=np.zeros(nentries)
#
ibox=np.full(nentries,0)
delt=np.zeros(nentries)
x=np.zeros(nxy)
y=np.zeros(nxy)
nstart=np.full(nxy,0)
nend=np.full(nxy,0)
night_count=np.full(nentries,0)
CSQM=np.zeros(nentries)
SQM=np.zeros(nentries)
chisquared=np.zeros(nentries)
ctemp=np.zeros(nentries)
tempslope=np.zeros(nentries)
tempchisq=np.zeros(nentries)
slopetemp=np.zeros(nentries)
sigslopetemp=np.zeros(nentries)
Etempc=np.zeros(nentries)
Stempc=np.zeros(nentries)
volt=np.zeros(nentries)
freq=np.zeros(nentries)
temps=np.zeros(nentries)
moonalt=np.zeros(nentries)
night=np.full(nentries,0)
# want the following set to True for pd columns w/o whines
pd.options.mode.copy_on_write = True
# influxDB options
dficha='LKXtshm7XHpORxczh-ZHJ5JViRk1XDEZuj3YF2wMLHoWV4KafApd7yO6DgUCHp07f_VaRj8pIi8LvkGJSWJNZQ=='
gficha= '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'
url='https://us-east-1-1.aws.cloud2.influxdata.com'
bucket='DSNdata'
org='DSN'
#     All SQM or TESS site Information
#
cols_sites = ['long','lat','el','sensor','ihead','dark',
              'bright','Site']
infile_sites='ALLsites.csv'
frame_sites=pd.read_csv(infile_sites,header=None,skiprows=1,sep=',')
frame_sites.columns=cols_sites
frame_sites.index = np.arange(1, len(frame_sites) + 1)
# site data from ALLsites.csv
sensor_names=frame_sites.Site
#print("\t\tKnown sites\n","Site No.\t\t Name")
#print(sensor_names)
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
# obscure but works, to get UTC, df contains frame_sensor.Tloc
    df=frame_sensor.copy()
    tloc=[dt.strftime(dt.strptime(str(df.Tloc.iloc[i]),'%y%m%d%H%M'),
        '%Y-%m-%dT%H:%M:%S') for i in range(len(df))]
    ut=[str(dt.strptime(tloc[i], '%Y-%m-%dT%H:%M:%S').\
            astimezone(datetime.timezone.utc))[:-6] \
            for i in range(len(df))]
    df.insert(0,'UT', ut )
    df.drop(['Tloc'],axis=1,inplace=True)
    df.insert(1,'Tloc',tloc)
#    df_cols=df.columns # reset column heading
    return ut,df#,df_cols
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
#    sqtemp=SQM[ns:ne+1]
        n1=ns
        n2=n1+ndata+ndata
        n3=ne-ndata-ndata
#        print(ii,n1,n2+1,n3,n3-n2-1)

# low end, fit hndata points instead of full ndata
        chisquared[n1:n2+1]= \
            [mycurve_fit(JD[nn:nn+hndata],SQM[nn:nn+hndata],hndata,2)#dark[nn]) 
                for nn in range(n1,n2+1)]
# main, fit ndata points
        chisquared[n2+1:n3] = [mycurve_fit(JD[nn-hndata:nn+hndata],
            SQM[nn-hndata:nn+hndata],ndata,1)#dark[nn]) 
                for nn in range(n2+1,n3)]
# high end, fit hndata points instead of full ndata
        chisquared[n3:ne+1]=[mycurve_fit(JD[nn-hndata:nn],
            SQM[nn-hndata:nn],hndata,2)#dark[nn]) 
                for nn in range(n3,ne+1)]
    return np.around(chisquared,5)
##################################################################
#MAIN: 
#Ingest raw SQM or TESS files, generate standardized csv tables for
#analysis and graphics
#
if len(sys.argv) > 1:
    in_file= sys.argv[1]
else:
    print('Argument missing: SQM/TESS input file, try again.')
    quit()
print('Input file :',in_file)
# find the site number
site_dict = {idx: el for idx, el in enumerate(sensor_names.values)}
islash=12 # after DSNdata/NEW
iunder=in_file.find('_')
matches = process.extract(in_file[islash:iunder], site_dict, limit=1)
site_number=matches[0][2]+1
site_name=in_file[islash:iunder]
print("Site name: ",site_name," Number ",site_number)
#
sensor_name = frame_sites.sensor.iloc[site_number-1].strip()
print("Sensor name ",sensor_name)
#
if (site_number == 6): print( 'TESS Bin has added line to the header')
if (site_number == 6): print( 'Check sign --temperature')
if (site_number == 7): print( 'TESS Bin has added line to the header')
if (site_number == 7): print( 'Check sign --temperature')
if (site_number == 8): print( 'TESS Bin has added line to the header')
if (site_number == 8): print( 'Check sign --temperature')
if (site_number == 9): print( 'TESS Bin has added line to the header')
if (site_number == 9): print( 'Check sign --temperature')
if (site_number == 10): print( 'TESS Bin has added line to the header')
if (site_number == 10): print( 'Check sign --temperature')
if (site_number == 13): print( 'TESS Bin has added line to the header')
if (site_number == 13): print( 'Check sign --temperature')
if (site_number == 14): print( 'Check sign --temperature')
if (site_number == 15): print( 'Check sign --temperature')
if (site_number == 16): print( 'Check sign --temperature')
#
#
start_time=time.time()
tlong = frame_sites.long.iloc[site_number-1]
tlat = frame_sites.lat.iloc[site_number-1]
#  elevation in meters above sea level
tele = frame_sites.el.iloc[site_number-1]

#  ndata is number of points used in cloud detection
# For 5 min spaced data
# ndata = 25 gives an hour on each side of a data point
# ndata = 19 gives 45 min on each side of a data point
# For 1 min spaced data
# ndata = 39  gives 17 min on each side of data point

# However this eliminates the Milky Way as the beam passes through it
# try 49 which gives 24 min on either side
#  Sugarloaf CNP Arizona has 10 min spacing
if (site_number == 11): ndata = 9 
#  chisqlimit used in cloud detection
#  picked so as not to skip part of the Milky Way on a photometric night
chisqlimit=0.009
# Dark Limit for mpsas ( clouds and fog)
darklimit = frame_sites.dark.iloc[site_number-1]
# Bright Limit for mpsas (light pollution in fog)
brightlimit = frame_sites.bright.iloc[site_number-1]
#  number of header lines
if ihead==-1:
    ihead=1
else:
    ihead = frame_sites.ihead.iloc[site_number-1]
#     moon not in sky =0 sun between astronomical twilights 0
#     cloud free sky = 0.00
# 
#  Read In the Data
#  Open the input file for reading
#  This next part opens the file to read from input file
#  
i_file=open(in_file,'r')
# 2 sensor types
sepcol=';'
# for chisquared measurement
tempdata = 19
if sensor_name == 'SQM': 
    frame_cols=['UT','Tloc','Etempc','volt','SQM','irec']
if site_number == 11: # Sugarloaf
    tempdata = 11
    frame_cols=['Tloc','Solar','Winds','Windd','Etempc','RH','Barom',
        'Precip','SQM','Stempc','Battery','Dtempc']
if site_number == 12: # Bonita
    frame_cols=['Tloc','Solar','Winds','Windd','Etempc','RH','Barom',
        'Precip','SQM','Stempc','Battery','Dtempc']
if sensor_name == 'SQM2': # NOIRLab
    frame_cols=['UT','Tloc','Etempc','counts','freq','SQM']
# UTC Date & Time, Local Date & Time, Temperature, Counts, Frequency, MSAS
# YYYY-MM-DDTHH:mm:ss.fff;YYYY-MM-DDTHH:mm:ss.fff;Celsius;number;Hz;mag/arcsec^2

if sensor_name == 'TESS':
    frame_cols=['UT','Tloc','Etempc','Stempc','freq','SQM','ZP']
if sensor_name == 'TESS1':
    frame_cols=['UT','Tloc','Etempc','Stempc','SQM']
ndata=tempdata # default
head_skip=3
if site_number == 19: head_skip=0 # special case of TESS data from John B
#
# frame_sensor is a dataframe with the data from input file(s)
if sensor_name == 'SQM1' or sensor_name == 'TESS1': # .xlsx data
    frame_sensor=pd.read_excel(in_file,header=head_skip)
    frame_sensor_add=pd.DataFrame(columns=frame_cols)
else:
    frame_sensor=pd.read_csv(in_file,header=None,skiprows=ihead,sep=sepcol)
    frame_sensor.columns=frame_cols

if sensor_name[:4] == 'TESS': # for normal TESS and for JB special
    df=frame_sensor
    frame_sensor = df[df.index % 5 == 0] 
    frame_sensor.reset_index(inplace=True,drop=True)
if sensor_name == 'SQM1':
    UT,frame_sensor = tloc_ut(frame_sensor)
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
if (site_number==4 or site_number==5 or site_number==9 or
    site_number==10 or site_number==11 or site_number==15 or 
    site_number==19): # for AZ
    df=frame_sensor[['UT','Tloc']]
    ut_tloc=(pd.to_datetime(df.UT)-pd.to_datetime(df.Tloc))/\
            pd.Timedelta(hours=1)
    ut_tloc_bad=np.where(ut_tloc!=7)[0]
    if (len(ut_tloc_bad)>0):
        df.Tloc=pd.to_datetime(df.UT).dt.tz_localize('Etc/GMT-7')
        df.Tloc=df.Tloc.dt.tz_convert(None)        
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
if (site_number==16 or site_number==17): # for Oregon
    df=frame_sensor[['UT','Tloc']]
    ut_tloc=(pd.to_datetime(df.UT)-pd.to_datetime(df.Tloc))/\
            pd.Timedelta(hours=1)
    ut_tloc_dst=np.where(ut_tloc==8)[0]
    JD_midnight_dst=np.around(JD_midnight+1./24.,6) # OR UT midnight for DST
    JD_midnight_2[ut_tloc_dst]=JD_midnight_dst
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
    raise UserWarning('JD not monotonic, QUIT')

# new altsun uses astropy sun routines
sunalt = altsun1(tlat,tlong,tele,list(UTC)) # calculates the whole vector of values

# Set the Sun flag to 0 when Sun below one of the angles below...
sun_dark = -18.
sun_8 = -8.0 # allow brighter sun at this stage (mainly SQM1)
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
    if (nend1[i]-nstart1[i]<nst_thr): ijump=10
    nsun[nstart1[i]:nend1[i]+1]=ijump
nst_index=[i for i in range(icount) if nsun[i]==0]
#####################################
# FILTERED nights
#####################################
print('Number of entries ',icount,' after filtering: ',len(nst_index))
icount=len(frame_sensor)
# cleanup sunalt, FINAL VERSION
nst_index=[i for i in range(icount) if nsun[i]==0] # reset it once again!
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
UTC_strip=[str(UTC[i]).strip().replace("T"," ") for i in range(len(UTC))]
#
if sensor_name == 'TESS1' : # special case
    Stempc = frame_sensor.Stempc
    freq = Stempc*0
    Etempc=frame_sensor.Etempc
else:
    Etempc=frame_sensor.Etempc
if sensor_name == 'SQM' :
    volt=frame_sensor.volt
    irec=frame_sensor.irec
if sensor_name == 'SQM1':
    volt=frame_sensor.Battery
    wind=frame_sensor.Winds
if sensor_name == 'SQM2':
    freq=frame_sensor.freq
    counts=frame_sensor.counts
if sensor_name == 'TESS' :
    Stempc = frame_sensor.Stempc
    freq = frame_sensor.freq
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
SQM_zero=np.where(SQM<=0)[0]
for ii in SQM_zero:
    if ii<icount-1:
        SQM[ii]=(SQM[ii-1]+SQM[ii+1])/2
    else:
        SQM[ii]=SQM[ii-1]

print("*** Averaged ",len(SQM_zero)," SQM values")
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
print('*** chisqlimit for cloud detection = ',chisqlimit)
#
# Determine the start and end points of astronomical twilight
# for each night, look for change from <sun_dark to >sun_dark
ii=0
nstart=np.full(inight,0)
nend=np.full(inight,0)
for i in nstart1:
    i2=nend1[ii]+1
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
             for j in range(nstart1[i],nend1[i]+1)]
# calculate chisquared, with interpolation at beg, end of night
start_time=time.time()
#
chisquared = np.zeros(icount)
#
for ii in range(inight):
    ns=nstart1[ii]
    ne=nend1[ii]
#    sqtemp=SQM[ns:ne+1]
    n1=ns
    n2=n1+ndata+ndata
    n3=ne-ndata-ndata
# low end, fit hndata points instead of full ndata
    chisquared[n1:n2+1]= \
        [mycurve_fit(JD[nn:nn+hndata],SQM[nn:nn+hndata],hndata,2)#dark[nn]) 
            for nn in range(n1,n2+1)]
# main, fit ndata points
    chisquared[n2+1:n3] = [mycurve_fit(JD[nn-hndata:nn+hndata],
        SQM[nn-hndata:nn+hndata],ndata,1)#dark[nn]) 
            for nn in range(n2+1,n3)]
# high end, fit hndata points instead of full ndata
    chisquared[n3:ne+1]=[mycurve_fit(JD[nn-hndata:nn],
        SQM[nn-hndata:nn],hndata,2)#dark[nn]) 
                         for nn in range(n3,ne+1)]
#
run_time = time.time()-start_time
print("+++ RUN time after cloud filter (sec): ",np.around(run_time,2))
start_time=time.time()
#  Open the output file for writing
#  This next part opens the file to write into for
#  putting into a spread sheet and data base
# create output file name from input file
# for influxDB
influx_file="DSNdata/PROCESSED/DSN-"+ in_file[12:in_file.find(".")]+".csv"
print("InfluxDB file name ",influx_file)
# write influxdb file header
ofile=open(influx_file,'w')
_=ofile.write('#group,false,false,false,false,true,true\n')
_=ofile.write('#datatype,string,long,dateTime:RFC3339,double,string,string\n')
_=ofile.write('#default,,,,,,\n')
ofile.close()
# populate dataframe df
cols_df=['UTC','SQM','lum','chisquared','moonalt']
df=pd.DataFrame(columns=cols_df)
df.UTC=[UTC_strip[i].replace(".000","") for i in range(icount)]
df.SQM=SQM
# calculate luminance
lum=[fnwcm2sr*10**((mag_ref-SQM[ii])/2.5) for ii in range(icount)]
df.lum=lum
df.chisquared=chisquared
df.moonalt=moonalt
df.UTC=[dt.strftime(dt.strptime(str(df.UTC.iloc[i]),
        '%Y-%m-%d %H:%M:%S'),'%Y-%m-%dT%H:%M:%SZ') 
            for i in range(len(df.UTC))]
for second in ['SQM','lum','chisquared','moonalt']:
#    print("doing ",second)
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
    df1['_measurement']=site_name
#
#   write header only when second=='SQM'
    df1.to_csv(influx_file,mode='a', header=(second=='SQM'),index=False)
print("Wrote ",len(df1)," entries to ",influx_file)
# github commands to commit influx_file
#g = Github(gficha)
#repo = g.get_repo('soazcomms/soazcomms.github.io')
#try: 
#    contents = repo.get_contents(influx_file)
#except GithubException as e:
#    print(f"Error: {e.data['NO file '+influx_file]}")
    # Handle the error or exit gracefully
#    exit(1)
#repo.update_file(contents.path, "Updating file via PyGithub",influx_file, contents.sha)
#
##################
# write influxdb file header
ofile=open(influx_file,'w')
_=ofile.write('#group,false,false,false,false,true,true\n')
_=ofile.write('#datatype,string,long,dateTime:RFC3339,double,string,string\n')
_=ofile.write('#default,,,,,,\n')
ofile.close()
# populate dataframe df
cols_df=['UTC','SQM','lum','chisquared','moonalt']
df=pd.DataFrame(columns=cols_df)
df.UTC=[UTC_strip[i].replace(".000","") for i in range(icount)]
df.SQM=SQM
# calculate luminance
lum=[fnwcm2sr*10**((mag_ref-SQM[ii])/2.5) for ii in range(icount)]
df.lum=lum
df.chisquared=chisquared
df.moonalt=moonalt
df.UTC=[dt.strftime(dt.strptime(str(df.UTC.iloc[i]),
        '%Y-%m-%d %H:%M:%S'),'%Y-%m-%dT%H:%M:%SZ') 
            for i in range(len(df.UTC))]
for second in ['SQM','lum','chisquared','moonalt']:
#    print("doing ",second)
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
    df1['_measurement']=site_name
#
#   write header only when second=='SQM'
    df1.to_csv(influx_file,mode='a', header=(second=='SQM'),index=False)
print("Wrote ",len(df1)," entries to ",influx_file)
#
