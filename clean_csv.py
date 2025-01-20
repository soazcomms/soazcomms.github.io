import csv

input_file = "DSNdata/INFLUX/DSN-MtLemmon_23.csv"
output_file = "DSNdata/INFLUX/DSN-MtLemmon_23_clean.csv"

with open(input_file, 'r') as infile, open(output_file, 'w', newline='') as outfile:
    reader = csv.reader(infile)
    writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
    for row in reader:
        writer.writerow(row)
