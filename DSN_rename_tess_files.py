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

def rename_files_and_update_table(tess_folder, tess_table_path):
    """Rename files using the Site name and update \
       TESStable.csv with incremented sequence numbers."""

    if not os.path.exists(tess_table_path):
        print(tess_table_path," not found, Skip.")
        return
#
    tess_table = pd.read_csv(tess_table_path)
    tess_table.columns = ['Site', 'Sequence','Alias']
#
    site_name = os.path.basename(tess_folder)
    row = tess_table.loc[tess_table['Site'] == site_name]
    if row.empty:
        print(f"Site {site_name} not found in TESStable.csv, Skip.")
        return
#
    seq_number = int(row['Sequence'].values[0])
#
    for filename in os.listdir(tess_folder):
        file_path = os.path.join(tess_folder, filename)
        with open(file_path,"r") as f:
            content=f.read()
        marker = "# END OF HEADER"
        if marker in content:
            parts = content.split(marker, 1)
            # If after marker is non-blank, insert newline
            if parts[1] and not parts[1].startswith("\n"):
                content = parts[0] + marker + "\n" + parts[1]
            # Save back
            with open(file_path, "w") as f:
                f.write(content)
        # Extract year from file
        year = extract_year_from_file(file_path)
        # Increment sequence number
        seq_number += 1
        tess_table.loc[tess_table['Site'] == site_name, 'Sequence'] = seq_number  # Update sequence
        # Create new filename
        new_filename = f"{site_name}_{year}_{seq_number:03d}.dat"
        new_filepath = os.path.join(tess_folder, new_filename)
        # Rename the file
        os.rename(file_path, new_filepath)
        print(f"Renamed: {filename} -> {new_filename}")
    # Save updated TESStable.csv
    tess_table.to_csv(tess_table_path, index=False)
    print("Updated TESStable.csv with new sequence numbers.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python DSNrename_tess_files.py \
        <DESTINATION_FOLDER> <TESS_TABLE> ")
        sys.exit(1)

    tess_folder = sys.argv[1]
    tess_table_path = sys.argv[2]
    rename_files_and_update_table(tess_folder, tess_table_path)
