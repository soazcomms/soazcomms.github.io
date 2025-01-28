# DSN.github.io

The Dark Sky Network (DSN): covering Southern Arizona to monitor  
the night sky brightness for the next several years, starting in 2025.

SQM/TESS raw data are uploaded to DSNdata/NEW. This process may be manual
(e.g. SQMs w/o internet) or automatic. The files are labeled with the sensor
name, e.g. DSN001_yy.dat where yy is the year when the data are obtained.

The GitHub workflow DSN-process_data.yml runs every day at 17:00 UTC. 

DSN-process_data looks for data in DSNdata/NEW. If it finds data there, 
it runs DSN_V03.py on each file to calculate chisquared and moonalt. 
Its output for each file is a .csv file in DSNdata/INFLUX, e.g. 
INF-DSNnnn_SiteName_yy.csv. DSN_V03 also writes to a .csv file with UTC, SQM, lum, 
chisquared and moonalt to DSNdata/BOX. If there is a previous .csv
file DSNnnn_SiteName_yy.csv, the new data are appended.

The .csv format is appropriate for input to influxDB, which 
feeds into Grafana for visualization. Each .csv file is uploaded into
influxDB. 

Once each .dat file is processed, the file in DSNdata/NEW is deleted. 

The files in DSNdata/BOX are uploaded to Box, in the DSNdata/ARCHIVE
folder. This is a permanent repository of the processed data.

A log of these file operations is written to DSNdata/RUN_LOG.
