#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
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
sites_df = pd.read_csv("DSNsites.csv", comment='#', header=None,
                       names=['lon', 'lat', 'el', 'sensor', 'ihead', 'dark',
                              'bright', 'label'])

# Extract label w/o site name
sites_df['label_strip'] = sites_df['label'].str.strip().str[:8]

# Lookup site info by label
try:
    site_info = sites_df[sites_df['label_strip'] == label].iloc[0]
    site = site_info['label']
    lon = site_info['lon']
    lat = site_info['lat']
    el = site_info['el']
    latlonel='Lon '+str(lon)+' Lat '+str(lat)+' El (m) '+str(el)
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

# Stats
df_local = df_all.copy()
df_local['Local'] = df_local['UTC'].dt.tz_convert('America/Phoenix')
df_local['Date'] = df_local['Local'].dt.date
#
night_df = df_local[(df_local['Local'].dt.hour >= 18) | (df_local['Local'].dt.hour <= 6)]
night_diff = (df_all['UTC'].iloc[1]-df_all['UTC'].iloc[0]).total_seconds()
night_hours = (len(night_df)-1)*night_diff/3600
pct_night = 100 * night_hours / run_hours if run_hours else 0

summary_html = f"""
<h2>1. Annual Summary Statistics</h2>
<ul>
  <li><b>Site:</b> {site}</li>
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
    jelly_df,
    x="hour_shifted",
    y="SQM",
    nbinsx=48,
    nbinsy=100,
    title="Jellyfish NSB in mag/arcsec²",
    labels={"hour_shifted": "Nightly MST", "SQM": "NSB mag/arcsec²"},
)

# Define tick positions and labels from 18.0 to 30.0 in 1-hour steps
tick_vals = list(range(18, 31))  # 18 to 30 inclusive
tick_text = [str(h if h < 24 else h - 24) for h in tick_vals]  # 24→0, ..., 30→6

fig_jelly.update_layout(
    xaxis=dict(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_text,
        title="MST (18h–6h)"
    )
)
# Save plot
fig_jelly.write_image("plot3_jellyfish.png", width=1000, height=600, scale=2)

# --- HEATMAP PLOT (FULL RANGE, MST LOCAL TIME) ---
# Step 1: Prepare data
heatmap_df = df_all.copy()
heatmap_df['MST'] = heatmap_df['UTC'].dt.tz_convert('America/Phoenix')
heatmap_df['hour'] = heatmap_df['MST'].dt.hour
heatmap_df['minute'] = heatmap_df['MST'].dt.minute
heatmap_df['date'] = heatmap_df['MST'].dt.date

# Filter only 18:00–23:59 and 00:00–05:59
mask = ((heatmap_df['hour'] >= 18) | (heatmap_df['hour'] < 6))
heatmap_df = heatmap_df[mask].copy()

# Create a label like "HH:MM" and group into 10-minute bins
heatmap_df['minute_of_day'] = heatmap_df['hour'] * 60 + heatmap_df['minute']
heatmap_df['minute_bin'] = (heatmap_df['minute_of_day'] // 10) * 10
heatmap_df['minute_label'] = heatmap_df['minute_bin'].apply(
    lambda m: f"{(m // 60) % 24:02d}:{m % 60:02d}"
)

# Reorder Y-axis: 18:00–23:50 followed by 00:00–05:50
labels_18_24 = [f"{h:02d}:{m:02d}" for h in range(18, 24) for m in range(0, 60, 10)]
labels_00_06 = [f"{h:02d}:{m:02d}" for h in range(0, 6) for m in range(0, 60, 10)]
ordered_labels = labels_18_24 + labels_00_06

# Keep only minute_labels in this order
heatmap_df = heatmap_df[heatmap_df['minute_label'].isin(ordered_labels)]

# Pivot: rows = minute_label, columns = date
pivot = heatmap_df.pivot_table(index='minute_label', columns='date', values='SQM', aggfunc='mean')
pivot = pivot.reindex(ordered_labels)  # enforce label order

# Plotting
fig_heatmap, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(pivot, cmap='viridis', ax=ax, cbar_kws={'label': 'SQM'}, xticklabels=1, yticklabels=6)

# Fix labels
ax.set_title("Heatmap of SQM (MST 18:00–06:00, 10-minute bins)", fontsize=13)
ax.set_xlabel("Date", fontsize=11)
ax.set_ylabel("Local Time (MST)", fontsize=11, labelpad=10)
ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=8)
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=8)
ax.yaxis.set_label_position("left")
ax.yaxis.set_label_coords(-0.08, 0.5)

plt.tight_layout()
fig_heatmap.savefig("plot4_heatmap.png", dpi=150)
plt.close(fig_heatmap)

# Embed in HTML
with open("plot4_heatmap.html", "w") as f:
    f.write("""
    <h2>4. Heatmap (SQM from 18:00 to 06:00 MST, 10-min bins)</h2>
    <img src="plot4_heatmap.png" width="100%" alt="Heatmap of SQM values">
    """)
    
# Sigma histogram
fig_sigma = px.histogram(df_all, x='chisquared', nbins=100,
                         title="chisquared Histogram")

# Save interactive HTML
pio.write_html(fig_hist, file="plot2_histogram.html",
               include_plotlyjs='cdn', full_html=False)
pio.write_html(fig_jelly, file="plot3_jellyfish.html",
               include_plotlyjs='cdn', full_html=False)
pio.write_html(fig_sigma, file="plot5_sigma.html",
               include_plotlyjs='cdn', full_html=False)

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
