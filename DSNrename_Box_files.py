import os
import pandas as pd
import re
import sys

def extract_alias(filename):
    return filename.split("/")[-1]

def match_alias_to_site(alias, table_df):
    row = table_df[table_df["Alias"] == alias]
    if not row.empty:
        return row.iloc[0]["Site"]
    return None

def extract_year_from_file(filepath):
    """Extracts the first two digits of the year (YY) from the first data entry after # comments."""
    try:
        with open(filepath, 'r') as file:
            for line in file:
                if not line.startswith('#'):
                    match = re.search(r'\b(20\d{2})\b', line)  # Match a year (e.g., 2025)
                    if match:
                        return match.group(1)[2:]  # Return last two digits of year
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
    return "00"  # Default if no year is found

def extract_year(filename):
    match = re.search(r'\b(19|20)\d{2}\b', filename)
    if match:
        return int(match.group(0))
    else:
        return float('inf')  # For files with no year, put them at the end

def rename_files_and_update_table(sqm_folder, sqm_table_path):
    """Rename files using the Site name and update SQMtable.csv with incremented sequence numbers."""
    if not os.path.exists(sqm_table_path):
        print("SQMtable.csv not found!")
        sys.exit(1)

    sqm_table = pd.read_csv(sqm_table_path)
    sqm_table.columns = ['Site', 'Sequence','Alias']
    renamed_files = []
#    print(sqm_table)
    alias = extract_alias(sqm_folder)
    site_name = match_alias_to_site(alias, sqm_table)
#    print(alias,site_name)
    row = sqm_table.loc[sqm_table['Site'] == site_name]
#    print(row)
    if row.empty:
        print(f"Site {site_name} not found in SQMtable.csv, skipping.")
        return

    seq_number = int(row['Sequence'].values[0])
    # Sort the list by year
    sorted_files = sorted(os.listdir(sqm_folder), key=extract_year)

    for filename in sorted_files:
        file_path = os.path.join(sqm_folder, filename)
        with open(file_path, "r") as f:
            first_line = f.readline()
            rest = f.read()
        # Prepend '#' if not already present
        if not first_line.startswith("#"):
            first_line = "# " + first_line
        with open(file_path, "w") as f:
            f.write(first_line + rest)
        # Extract year from file
        year = extract_year_from_file(file_path)
        # Increment sequence number
        seq_number += 1
        sqm_table.loc[sqm_table['Site'] == site_name, 'Sequence'] = seq_number  # Update sequence

        # Create new filename
        new_filename = f"{site_name}_{year}_{seq_number:03d}.dat"
        new_filepath = os.path.join(sqm_folder, new_filename)

        # Rename the file
        os.rename(file_path, new_filepath)
        print(f"Renamed: {filename} -> {new_filename}")
        renamed_files.append(new_filename)

    # Save updated SQMtable.csv
    sqm_table.to_csv(sqm_table_path, index=False)
    print("Updated SQMtable.csv with new sequence numbers.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python DSNrename_sqm_files.py <SQM_FOLDER> <SQM_TABLE_PATH>")
        sys.exit(1)

    sqm_folder = sys.argv[1]
    sqm_table_path = sys.argv[2]
    rename_files_and_update_table(sqm_folder, sqm_table_path)
    sqm_table = pd.read_csv(sqm_table_path)

