# DSN.github.io
Dark Sky Network (DSN)
SQM/TESS raw data are uploaded to DSNdata/NEW. This process may be manual
(e.g. SQMs w/o internet) or automatic. The files are labeled with the sensor
name, e.g. DSN001_yy.dat where yy is the year when the data are obtained.
A cron job, DSN-process_data.yml, runs every day at 17:00 UTC. 
DSN-process_data looks for data in DSNdata/NEW. It runs DSN_V02.py 
on the .dat files to calculate chisquared and moonalt. Its output is 
a .csv file in DSNdata/INFLUX, e.g. DSN001_yy.csv. Its format is 
appropriate for input to influxDB, which feeds into Grafana for 
visualization. Once each .dat file is processed, it is moved to 
DSNdata/ARCHIVE, or appended to any existing .dat file for each
unit (e.g. DSN001) and year yy.
