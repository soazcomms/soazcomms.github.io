# DSN.github.io

The Dark Sky Network (DSN): covering Southern Arizona to monitor  
the night sky brightness for the next several years, starting in 2025.

SQM/TESS raw data are uploaded to DSNdata/NEW. This process may be manual
(e.g. SQMs w/o internet) or automatic. The files are labeled with the sensor
name, e.g. DSN001_yy.dat where yy is the year when the data are obtained.

A cron job, DSN-process_data.yml, runs every day at 17:00 UTC. 
DSN-process_data looks for data in DSNdata/NEW. If it finds data there, 
it runs DSN_V02.py on each .dat file to calculate chisquared and moonalt. 
Its output for each .dat file is a .csv file in DSNdata/INFLUX, e.g. 
DSN001_yy.csv. 

The .csv format is appropriate for input to influxDB, which 
feeds into Grafana for visualization. Each .csv file is uploaded into
influxDB. 

Once each .dat file is processed, it is moved to DSNdata/ARCHIVE, or 
appended to any existing .dat file for therein, corresponding to each
unit (e.g. DSN001) and year yy.
