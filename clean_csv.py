input_file = "DSNdata/INFLUX/DSN-MtLemmon_23.csv"
output_file = "DSNdata/INFLUX/DSN-MtLemmon_23_clean.csv"

def clean_value(value):
    if '"' in value:
        value = value.replace('"', '""')
    if ',' in value or '\n' in value:
        value = f'"{value}"'
    return value

with open(input_file, 'r') as infile, open(output_file, 'w', newline='')\
     as outfile:
    reader = csv.reader(infile)
    writer = csv.writer(outfile, quoting=csv.QUOTE_NONE, escapechar='\\')
    for row in reader:
        cleaned_row = [clean_value(field) for field in row]
        writer.writerow(cleaned_row)
