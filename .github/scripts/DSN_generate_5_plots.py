import os
import glob
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument('--input_dir', required=True)
parser.add_argument('--from', dest='from_time', required=True)
parser.add_argument('--to', dest='to_time', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()

start_time = pd.to_datetime(args.from_time, utc=True)
end_time = pd.to_datetime(args.to_time, utc=True)
label = args.label.replace('–', '-').replace('—', '-')
# Find all matching files
files = sorted(glob.glob(os.path.join(args.input_dir, f"{label}_*.csv")))
if not files:
    print(f"❌ No files found for label {label}")
    sys.exit(1)

# Load and concatenate all data
df_list = []
for file in files:
    sep = ';' if label.endswith('T') else ','
    df_temp = pd.read_csv(file, sep=sep, parse_dates=['UTC'], on_bad_lines='skip')
    df_list.append(df_temp)

df = pd.concat(df_list, ignore_index=True)
df['UTC'] = pd.to_datetime(df['UTC'], utc=True, errors='coerce')

# Filter full set by time range
df = df[(df['UTC'] >= start_time) & (df['UTC'] <= end_time)]

if df.empty:
    print(f"⚠️ No data found for label {label} in range {start_time} to {end_time}. Exiting.")
    sys.exit(0)

df['UTC'] = pd.to_datetime(df['UTC'], utc=True, errors='coerce')
df = df[(df['UTC'] >= start_time) & (df['UTC'] <= end_time)]

# Plot 1: Time Series
plt.figure(figsize=(10, 4))
plt.plot(df['UTC'], df['SQM'])
plt.xlabel('UTC')
plt.ylabel('SQM')
plt.title('Brightness Over Time')
plt.tight_layout()
plt.savefig('plot1_timeseries.png')
plt.close()

# Plot 2: Histogram
plt.figure(figsize=(6, 4))
plt.hist(df['SQM'].dropna(), bins=50)
plt.xlabel('SQM')
plt.ylabel('Count')
plt.title('Histogram of SQM')
plt.tight_layout()
plt.savefig('plot2_histogram.png')
plt.close()

# Plot 3: Jellyfish (binned heatmap of time-of-day vs SQM)
df['hour'] = df['UTC'].dt.hour + df['UTC'].dt.minute / 60.0
df['hour_local'] = ((df['hour'] - 7) + 24) % 24  # UTC to MST
hbins = pd.cut(df['hour_local'], bins=range(17, 32), right=False, include_lowest=True)
sbins = pd.cut(df['SQM'], bins=100)
jelly = pd.crosstab(hbins, sbins)

plt.figure(figsize=(10, 6))
plt.imshow(jelly.T, aspect='auto', origin='lower', cmap='viridis')
plt.colorbar(label='Count')
plt.xlabel('Hour (MST)')
plt.ylabel('SQM')
plt.title('Jellyfish Plot')
plt.tight_layout()
plt.savefig('plot3_jellyfish.png')
plt.close()

# Plot 4: Heatmap of mean SQM per hour
mean_sqm = df.groupby(df['hour_local'].round()).SQM.mean()
plt.figure(figsize=(8, 4))
plt.bar(mean_sqm.index, mean_sqm.values)
plt.xlabel('Hour (MST)')
plt.ylabel('Mean SQM')
plt.title('Mean SQM by Hour')
plt.tight_layout()
plt.savefig('plot4_heatmap.png')
plt.close()

# Plot 5: Sigma Histogram
sigma = df['SQM'].std()
plt.figure(figsize=(6, 4))
plt.hist((df['SQM'] - df['SQM'].mean()) / sigma, bins=50)
plt.xlabel('Standard Deviations from Mean')
plt.ylabel('Count')
plt.title('Sigma Histogram')
plt.tight_layout()
plt.savefig('plot5_sigma.png')
plt.close()

# HTML dashboard output
html = f"{label}.analysis.html"
with open(html, 'w') as f:
    f.write(f"""
<!DOCTYPE html>
<html>
<head>
    <title>{label} - Southern Arizona Dark Sky Network</title>
    <meta charset="utf-8"/>
    <style>
        body {{ font-family: sans-serif; max-width: 1000px; margin: auto; }}
        img {{ width: 100%; border: 1px solid #ccc; margin-bottom: 20px; }}
        h2 {{ cursor: pointer; color: #006; }}
    </style>
    <script>
        function toggle(id) {{
            const el = document.getElementById(id);
            el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }}
    </script>
</head>
<body>
    <h1>{label} - Southern Arizona Dark Sky Network</h1>
    <p><b>Time range:</b> {start_time} to {end_time}</p>

    <h2 onclick="toggle('plot1')">1. Brightness Over Time (click to toggle)</h2>
    <img id="plot1" src="plot1_timeseries.png" alt="Time Series">

    <h2 onclick="toggle('plot2')">2. Histogram of SQM (click to toggle)</h2>
    <img id="plot2" src="plot2_histogram.png" alt="Histogram">

    <h2 onclick="toggle('plot3')">3. Jellyfish Plot (click to toggle)</h2>
    <img id="plot3" src="plot3_jellyfish.png" alt="Jellyfish Plot">

    <h2 onclick="toggle('plot4')">4. Heatmap (click to toggle)</h2>
    <img id="plot4" src="plot4_heatmap.png" alt="Heatmap">

    <h2 onclick="toggle('plot5')">5. Sigma Histogram (click to toggle)</h2>
    <img id="plot5" src="plot5_sigma.png" alt="Sigma Histogram">
</body>
</html>
""")
