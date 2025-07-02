import os
import pandas as pd
import re
import sys

def extract_year_from_file(filepath):
    """Extracts last two digits of the year (YY) from first data line """
    _, sqm_ext = os.path.splitext(filepath)
    sqm_ext = sqm_ext.lower()
    with open(filepath, "r") as f:
        for line in f:
            if not line.lstrip().startswith("#"):
                break
    if sqm_ext in ['.dat', '.csv']:
        with open(filepath, "r") as f:
            for line in f:
                if not line.lstrip().startswith("#"):
                    break
        match = re.search(r'20(\d{2})', line)  # Matches 20xx
        if match:
            return match.group(1)
    else:
        print(f"Error: file {filepath} wrong extension.")
        sys.exit(1)

    return
#
def rename_files_and_update_table(sqm_folder, sqm_table_path):
    """Rename files using the Site name and update \
       SQMtable.csv with incremented sequence numbers."""

    if not os.path.exists(sqm_table_path):
        print(sqm_table_path," not found, Skip.")
        return
#
    site_name = os.path.basename(sqm_folder)
    all_items = os.listdir(sqm_folder)
    if all(f.startswith("DSN") for f in all_items):
        print(f"Files in",sqm_folder," already labeled, Skip.")
        return
#
    sqm_table = pd.read_csv(sqm_table_path)
    sqm_table.columns = ['Site', 'Sequence','Alias']
#
    row = sqm_table.loc[sqm_table['Site'] == site_name]
    if row.empty:
        print(f"Site {site_name} not found in SQMtable.csv, Skip.")
        return
#
    seq_number = int(row['Sequence'].values[0])
#
    for filename in os.listdir(sqm_folder):
        file_path = os.path.join(sqm_folder, filename)
        _, sqm_ext = os.path.splitext(filename)
        # Extract year from file
        year = extract_year_from_file(file_path)
        # Increment sequence number
        seq_number += 1
        sqm_table.loc[sqm_table['Site'] == site_name, 'Sequence'] = seq_number  # Update sequence
        # Create new filename
        new_filename = f"{site_name}_{year}_{seq_number:03d}{sqm_ext}"
        new_filepath = os.path.join(sqm_folder, new_filename)
        # Rename the file
        os.rename(file_path, new_filepath)
        print(f"Renamed: {filename} -> {new_filename}")

    # Save updated SQMtable.csv
    sqm_table.to_csv(sqm_table_path, index=False)
    print("Updated SQMtable.csv with new sequence numbers.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python DSNrename_sqm_files.py \
        <DESTINATION_FOLDER> <SQM_TABLE> ")
        sys.exit(1)

    sqm_folder = sys.argv[1]
    sqm_table_path = sys.argv[2]
    rename_files_and_update_table(sqm_folder, sqm_table_path)
