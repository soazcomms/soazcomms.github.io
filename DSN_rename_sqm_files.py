import os
import pandas as pd
import re
import sys

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

def rename_files_and_update_table(sqm_folder, sqm_table_path):
    """Rename files using the Site name and update SQMtable.csv with incremented sequence numbers."""
    if not os.path.exists(sqm_table_path):
        print("SQMtable.csv not found!")
        sys.exit(1)

    sqm_table = pd.read_csv(sqm_table_path)
    sqm_table.columns = ['Site', 'Sequence','Alias']
    renamed_files = []

    site_name = os.path.basename(sqm_folder)
    row = sqm_table.loc[sqm_table['Site'] == site_name]

    if row.empty:
        print(f"Site {site_name} not found in SQMtable.csv, skipping.")
        return

    seq_number = int(row['Sequence'].values[0])

    for filename in os.listdir(sqm_folder):
        file_path = os.path.join(sqm_folder, filename)

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
        print("Usage: python DSNrename_sqm_files.py <SQM_FOLDER> <DESTINATION_FOLDER>")
        sys.exit(1)

    sqm_folder = sys.argv[1]
    sqm_table_path = sys.argv[2]
    rename_files_and_update_table(sqm_folder, sqm_table_path)
