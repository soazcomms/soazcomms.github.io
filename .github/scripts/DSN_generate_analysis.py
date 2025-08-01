#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.io as pio
from datetime import datetime, timedelta
import argparse
import os
import pytz
from glob import glob

# Argument parsing
parser = argparse.ArgumentParser()
parser.add_argument('--input_dir', required=True)
parser.add_argument('--from', dest='from_time', required=True)
parser.add_argument('--to', dest='to_time', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()

start_time = pd.to_datetime(args.from_time, utc=True)
end_time = pd.to_datetime(args.to_time, utc=True)
label = args.label.replace('–', '-').replace('—', '-')

# Load site metadata
sites_df = pd.read_csv("DSNdata/DSNsites.csv", comment='#', header=None,
                       names=['lon', 'lat', 'el', 'sensor', 'ihead', 'dark',
                              'bright', 'label'])

# Strip whitespace from labels in case they were misaligned
sites_df['label'] = sites_df['label'].str.strip().str[:8]

# Lookup site info by label
try:
    site_info = sites_df[sites_df['label'] == label].iloc[0]
    lon = site_info['lon']
    lat = site_info['lat']
    el = site_info['el']
except IndexError:
    raise ValueError(f"Label {label} not found in DSNsites.csv")

# Load CSVs
files = sorted(glob(os.path.join(args.input_dir, f"{label}_*.csv")))
if not files:
    raise FileNotFoundError(f"No files matching {label}_*.csv found in {args.input_dir}")

df_all = pd.concat(
    [pd.read_csv(f, sep=None, engine='python') for f in files],
    ignore_index=True
)

# Parse timestamps
df_all['UTC'] = pd.to_datetime(df_all['UTC'], utc=True, errors='coerce')
run_hours = (df_all['UTC'].iloc[-1]-df_all['UTC'].iloc[0]).total_seconds()/3600
df_all = df_all.dropna(subset=['UTC'])

# Filter by range
df_all = df_all[(df_all['UTC'] >= start_time) & (df_all['UTC'] <= end_time)]

if df_all.empty:
    raise ValueError("No data in selected range.")

# Extract coordinates
with open(files[0]) as f:
    lines = f.readlines()
    for line in lines:
        if line.startswith("# Position"):
            latlonel = line.split(":")[1].strip()
            break
    else:
        latlonel = "Unknown"

# Stats
df_local = df_all.copy()
df_local['Local'] = df_local['UTC'].dt.tz_convert('America/Phoenix')
df_local['Date'] = df_local['Local'].dt.date
#run_hours = len(df_local)/12  # assuming 5-min cadence
night_df = df_local[(df_local['Local'].dt.hour >= 18) | (df_local['Local'].dt.hour <= 6)]
night_diff = (df_all['UTC'].iloc[1]-df_all['UTC'].iloc[0]).total_seconds()/60
night_hours = len(night_df)*night_diff/60
pct_night = 100 * night_hours / run_hours if run_hours else 0

summary_html = f"""
<h2>1. Annual Summary Statistics</h2>
<ul>
  <li><b>Coordinates:</b> {latlonel}</li>
  <li><b>Time Range:</b> {start_time} to {end_time}</li>
  <li><b>Total Run Hours:</b> {run_hours:.2f}</li>
  <li><b>Night Hours (18–06 MST):</b> {night_hours:.2f}</li>
  <li><b>% Night:</b> {pct_night:.1f}%</li>
</ul>
"""

# Histogram
fig_hist = px.histogram(df_all, x="SQM", nbins=100, title="Histogram of SQM")

# Jellyfish
jelly_df = df_all.copy()
jelly_df['MST'] = jelly_df['UTC'].dt.tz_convert('America/Phoenix')
jelly_df['hour'] = jelly_df['MST'].dt.hour + jelly_df['MST'].dt.minute / 60
jelly_df['hour_shifted'] = jelly_df['hour'].apply(lambda h: h if h >= 18 else h + 24)
jelly_df['day'] = jelly_df['MST'].dt.date
fig_jelly = px.density_heatmap(
    jelly_df, x="hour_shifted", y="SQM", nbinsx=48, nbinsy=100,
    title="Jellyfish Plot for NSB in mag/asec^2", labels={"hour_shifted": "MST 18-6h)"}
)

# Heatmap (real 2D)
heatmap_df = jelly_df.copy()
heatmap_df['hour_bin'] = heatmap_df['hour_shifted'].round(1)
heatmap_df['sqm_bin'] = heatmap_df['SQM'].round(1)
pivot = heatmap_df.pivot_table(index='sqm_bin', columns='hour_bin', aggfunc='size', fill_value=0)
fig_heatmap = px.imshow(pivot.values, x=pivot.columns, y=pivot.index,
                        title="2D SQM Heatmap", labels={"x": "Hour", "y": "SQM bins"})

# Sigma histogram
fig_sigma = px.histogram(df_all, x='chisquared', nbins=100, title="chisquared Histogram")

# Save interactive HTML
pio.write_html(fig_hist, file="plot2_histogram.html", include_plotlyjs='cdn', full_html=False)
pio.write_html(fig_jelly, file="plot3_jellyfish.html", include_plotlyjs='cdn', full_html=False)
pio.write_html(fig_heatmap, file="plot4_heatmap.html", include_plotlyjs='cdn', full_html=False)
pio.write_html(fig_sigma, file="plot5_sigma.html", include_plotlyjs='cdn', full_html=False)

# Compose final HTML
with open(f"{label}.analysis.html", "w") as f:
    f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <title>{label} - Southern Arizona Dark Sky Network</title>
</head>
<body>
    <h1>{label} - Southern Arizona Dark Sky Network</h1>
    {summary_html}
    <h2>2. Histogram of SQM</h2>
    <iframe src="plot2_histogram.html" width="100%" height="400"></iframe>
    <h2>3. Jellyfish Plot</h2>
    <iframe src="plot3_jellyfish.html" width="100%" height="500"></iframe>
    <h2>4. Heatmap</h2>
    <iframe src="plot4_heatmap.html" width="100%" height="500"></iframe>
    <h2>5. Sigma Histogram</h2>
    <iframe src="plot5_sigma.html" width="100%" height="400"></iframe>
</body>
</html>
""")
