#!/usr/bin/env python3
import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime

# --- Parse arguments ---
parser = argparse.ArgumentParser(description="Generate 5 SQM plots from CSV files")
parser.add_argument("--input_dir", required=True)
parser.add_argument("--from", dest="from_time", required=True)
parser.add_argument("--to", dest="to_time", required=True)
parser.add_argument("--label", required=True)
parser.add_argument("--output", default="dashboard.html")
args = parser.parse_args()

start_time = pd.to_datetime(args.from_time, utc=True)
end_time = pd.to_datetime(args.to_time, utc=True)
label = args.label.replace("–", "-").replace("—", "-")  # normalize dash
output_file = args.output

# --- Load data ---
files = sorted([
    os.path.join(args.input_dir, f) for f in os.listdir(args.input_dir)
    if f.startswith(label) and f.endswith(".csv")
])

if not files:
    raise FileNotFoundError(f"No CSV files found for label {label} in {args.input_dir}")

df_list = []
for f in files:
    df = pd.read_csv(f, sep=None, engine='python')
    df['UTC'] = pd.to_datetime(df['UTC'], format='%Y-%m-%dT%H:%M:%SZ', utc=True, errors='coerce')
    df_list.append(df)

df = pd.concat(df_list)
df = df[(df['UTC'] >= start_time) & (df['UTC'] <= end_time)].copy()

if df.empty:
    raise ValueError("No data in selected time range.")

# --- Plot 1: Time series of SQM ---
plt.figure(figsize=(10, 4))
plt.plot(df['UTC'], df['SQM'], label="SQM", linewidth=0.7)
plt.title("SQM Over Time")
plt.xlabel("UTC Time")
plt.ylabel("mag/arcsec²")
plt.grid(True)
plt.tight_layout()
plt.savefig("plot1_timeseries.png")
plt.close()

# --- Plot 2: Histogram of SQM ---
plt.figure(figsize=(6, 4))
plt.hist(df['SQM'].dropna(), bins=50, color='gray', edgecolor='black')
plt.title("Histogram of SQM")
plt.xlabel("mag/arcsec²")
plt.ylabel("Count")
plt.tight_layout()
plt.savefig("plot2_histogram.png")
plt.close()

# --- Plot 3: Jellyfish plot (stacked time vs brightness) ---
df['hour'] = df['UTC'].dt.tz_convert("US/Arizona").dt.hour + df['UTC'].dt.tz_convert("US/Arizona").dt.minute / 60
df['day'] = df['UTC'].dt.date
pivot = df.pivot_table(index='hour', columns='day', values='SQM')

plt.figure(figsize=(12, 4))
plt.imshow(pivot, aspect='auto', origin='lower', extent=[
    pivot.columns.min().toordinal(), pivot.columns.max().toordinal(),
    pivot.index.min(), pivot.index.max()
], cmap='plasma')
plt.colorbar(label="mag/arcsec²")
plt.title("Jellyfish Plot (Time vs Brightness)")
plt.xlabel("Date")
plt.ylabel("Local Time (hours)")
plt.tight_layout()
plt.savefig("plot3_jellyfish.png")
plt.close()

# --- Plot 4: Heatmap (2D histogram) ---
H, xedges, yedges = np.histogram2d(
    df['hour'], df['SQM'], bins=[24, 40], range=[[0, 24], [df['SQM'].min(), df['SQM'].max()]]
)
plt.figure(figsize=(10, 4))
plt.imshow(H.T, origin='lower', aspect='auto',
           extent=[0, 24, df['SQM'].min(), df['SQM'].max()], cmap='viridis')
plt.colorbar(label="Count")
plt.title("Heatmap: SQM vs Local Hour")
plt.xlabel("Hour")
plt.ylabel("SQM")
plt.tight_layout()
plt.savefig("plot4_heatmap.png")
plt.close()

# --- Plot 5: Sigma Histogram (chisquared distribution) ---
plt.figure(figsize=(6, 4))
plt.hist(df['chisquared'].dropna(), bins=50, color='blue', edgecolor='black')
plt.title("Chi-squared Histogram")
plt.xlabel("Chi-squared")
plt.ylabel("Count")
plt.tight_layout()
plt.savefig("plot5_sigma.png")
plt.close()

# --- HTML dashboard output ---
html = f"{label}.analysis.html"
html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{label} - Southern Arizona Dark Sky Network</title>
    <meta charset="utf-8"/>
    <style>
        body {{
            font-family: sans-serif;
            max-width: 1000px;
            margin: auto;
        }}
        img {{
            width: 100%;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <h1>{label} - Southern Arizona Dark Sky Network</h1>
    <p><b>Time range:</b> {start_time} to {end_time}</p>
    <h2>1. Brightness Over Time</h2>
    <img src="plot1_timeseries.png" alt="Time Series">
    <h2>2. Histogram of SQM</h2>
    <img src="plot2_histogram.png" alt="Histogram">
    <h2>3. Jellyfish Plot</h2>
    <img src="plot3_jellyfish.png" alt="Jellyfish Plot">
    <h2>4. Heatmap</h2>
    <img src="plot4_heatmap.png" alt="Heatmap">
    <h2>5. Sigma Histogram</h2>
    <img src="plot5_sigma.png" alt="Sigma Histogram">
</body>
</html>
"""

with open(html, "w") as f:
    f.write(html_content)

print(f"✅ Dashboard generated: {html}")
