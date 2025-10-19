# Dark Sky Network
## DSN
The Dark Sky Network (DSN): monitoring the night sky brightness over Southern Arizona 
for the next ten years, starting in 2025. We use SQM and TESS units. Several units are in place, and have
been running for up to 7 years. Their data are periodically incorporated in our data space. 
We took delivery of SQM units on 2/6/25 and TESS units on 5/19/25. 
As of 10/19/25, we have 17 units in the DSN.
> [!CAUTION]
> This code is a work in progress.

# The Process
The GitHub workflow [**DSN-process_data**](https://github.com/soazcomms/soazcomms.github.io/blob/main/.github/workflows/DSN-process_data.V02.yml) runs weekly. If it finds data in the github directory DSNdata/NEW, it processes it (see below).

### Step 1
SQM/TESS raw data are uploaded to DSNdata/NEW. This process may be manual
(e.g. SQMs w/o internet) or automatic using a Raspberry Pi 4B. The files are labeled with the site and sensor name, DSNnnn-U_SiteName_yy-sss.dat where: 
* nnn is a site sequence number
* U is the type of the unit, S (T) for SQM (TESS)
* SiteName describes the site
* yy is the year when the data are obtained 
* sss is a sequence number for files uploaded each year

Two GitHub workflows harvest data for processing into DSNdata/NEW: 
- [**DSN-get-SQM**] runs weekly, finds and downloads new SQM data uploaded manually to a google drive that DSNsoaz owns. Ethernet-enabled SQM units eventually will also upload to the google drive. The new SQM data are also uploaded to Box, directory DSNdata/SQM.
+ [**DSN-get-TESS**] runs monthly, finds and downloads new TESS data from the Stars4All network.

A shell script outside GitHub harvests data into DSNdata/NEW, running on DSN-imac. 
- [**DSN-sync-box.sh**] runs monthly, finds and downloads new SQM data in Hannes Groller's Box repository.  
### Step 2
**DSN-process_data** looks for data in DSNdata/NEW. If it finds data there, 
it runs [DSN_python](https://github.com/soazcomms/soazcomms.github.io/blob/main/DSN_V03.py) on each file to calculate chisquared, moonalt and LST. 
1. For each file, **DSN_python** writes a .csv file in DSNdata/INFLUX, with the format DSNnnn-U_SiteName_yy-nn.csv.
2. For each file, **DSN_python** writes a .csv file with UTC, SQM, lum, chisquared, moonalt and LST to DSNdata/BOX.
These files are an archive of processed data.
### Step 3
The .csv format is appropriate for input to **influxDB**, which 
feeds into **Grafana** for visualization. Each .csv file is uploaded into
influxDB, and then deleted from DSNdata/INFLUX. Each .csv file that [DSN_python](https://github.com/soazcomms/soazcomms.github.io/blob/main/DSN_V03.py)
writes is tagged with the site label, DSNnnn-U_SiteName, for influxDB to include it in the appropriate "dashboard," 
each of which is specific to the site so that **Grafana** can display it.
### Step 4
Once each .dat file in DSNdata/NEW is processed it is deleted. 
### Step 5
Each file in DSNdata/BOX is uploaded to the Box repository, in the DSNdata/ARCHIVE
folder, and is deleted from DSNdata/BOX. Files are stored in the format DSNnnn-U_SiteName_yy.csv. 
This is intended as a long-term archive of the processed data.
### Step 6
A record of the file operations above is written to a running [LOG](https://github.com/soazcomms/soazcomms.github.io/blob/main/DSNdata/RUN_LOG).
# Visualizing data
The processed data may be visualized with 
<a href="https://soazcomms.github.io/DSNweb.v04.html" target="_blank">
  DSNweb
</a> (Use SHIFT-click to open in a new window.)
