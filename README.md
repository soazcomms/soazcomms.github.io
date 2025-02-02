# Dark Sky Network
## DSN
The Dark Sky Network (DSN): monitoring the night sky brightness over Southern Arizona 
for the next ten years, starting in 2025. We use SQM and TESS units, labeled DSNnnn,
where nnn runs from 000 to 032 as of 28 January 2025. Several units are extant, and have
been running for up to 7 years. Their data are being incorporated in our data space. More 
SQM and TESS units are being acquired, starting in January 2025.
## The Process
The GitHub workflow [DSN-process_data](https://github.com/soazcomms/soazcomms.github.io/blob/main/.github/workflows/DSN-process_data.V02.yml) runs every day at 17:00 UTC. 
- ### Step 1
SQM/TESS raw data are uploaded to DSNdata/NEW. This process may be manual
(e.g. SQMs w/o internet) or automatic. The files are labeled with the sensor
name, e.g. DSN001_SiteName_yy.dat where yy is the year when the data are obtained.
* ### Step 2
DSN-process_data looks for data in DSNdata/NEW. If it finds data there, 
it runs DSN_V03.py on each file to calculate chisquared and moonalt. 
Its output for each file is a .csv file in DSNdata/INFLUX, e.g. 
INF-DSNnnn_SiteName_yy.csv. DSN_V03 also writes to a .csv file with UTC, SQM, lum, 
chisquared and moonalt to DSNdata/BOX. If there is a previous .csv
file DSNnnn_SiteName_yy.csv, the new data are appended.
* ### Step 3
The .csv format is appropriate for input to influxDB, which 
feeds into Grafana for visualization. Each .csv file is uploaded into
influxDB. 
* ### Step 4
Once each .dat file is processed, the file in DSNdata/NEW is deleted. 
* ### Step 5
The files in DSNdata/BOX are uploaded to the Box repository, in the DSNdata/ARCHIVE
folder. This is intended as a permanent archive of the processed data.
+ ### Step 6
A log of these file operations is written to a running [LOG](https://github.com/soazcomms/soazcomms.github.io/blob/main/DSNdata/RUN_LOG).
