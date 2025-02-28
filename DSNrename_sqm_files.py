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

def rename_files_and_update_table(sqm_folder, dsn_table_path):
    # Load DSNtable.csv
    if os.path.exists(dsn_table_path):
        dsn_table = pd.read_csv(dsn_table_path)
        dsn_table.columns=(['Site','Sequence'])
    else:
        print("DSNtable.csv not found!")
        sys.exit(1)

    renamed_files = []
    
    for filename in os.listdir(sqm_folder):
        file_path = os.path.join(sqm_folder, filename)
        
        # Get site name and sequence number from DSNtable.csv
        for index, row in dsn_table.iterrows():
            site_name = row['Site']
            seq_number = int(row['Sequence'])
            
            # Extract year from file
            year = extract_year_from_file(file_path)
            
            # Increment sequence number
            new_seq_number = seq_number + 1
            dsn_table.at[index, 'Sequence'] = new_seq_number  # Update sequence in table
            
            # Create new filename
            new_filename = f"{site_name}_{year}_{new_seq_number:03d}.dat"
            new_filepath = os.path.join(sqm_folder, new_filename)
            
            # Rename the file
            os.rename(file_path, new_filepath)
            print(f"Renamed: {filename} -> {new_filename}")
            renamed_files.append(new_filename)
            break  # Process only one match per file
    
    # Save updated DSNtable.csv
    dsn_table.to_csv(dsn_table_path, index=False)
    print("Updated DSNtable.csv with new sequence numbers.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python rename_sqm_files.py <SQM_FOLDER> <DSNTABLE_CSV>")
        sys.exit(1)
    
    sqm_folder = sys.argv[1]
    dsn_table_path = sys.argv[2]
    rename_files_and_update_table(sqm_folder, dsn_table_path)
