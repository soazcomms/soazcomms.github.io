#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
import seaborn as sns
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
from datetime import datetime, timedelta
import argparse
import os
import json
import pytz
from glob import glob
import numpy as np

# Argument parsing
parser = argparse.ArgumentParser()
parser.add_argument('--input_dir', required=True)
parser.add_argument('--from', dest='from_time', required=True)
parser.add_argument('--to', dest='to_time', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()

in_dir=args.input_dir
start_time = pd.to_datetime(args.from_time, utc=True)
start_str = start_time.strftime("%y-%m-%d %H:%M:%S")
end_time = pd.to_datetime(args.to_time, utc=True)
end_str = end_time.strftime("%y-%m-%d %H:%M:%S")
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
    latlonel='Lon '+str(lon)+' Lat '+str(lat)+' El '+str(el)+' m'
except IndexError:
    raise ValueError(f"Label {label} not found in DSNsites.csv")

# Load CSVs
files = sorted(glob(os.path.join(in_dir, f"{label}_*.csv")))
if not files:
    raise FileNotFoundError(f"No files matching {label}_*.csv found in {in_dir}")

df_all = pd.concat(
    [pd.read_csv(f, sep=None, engine='python') for f in files],
    ignore_index=True
)
# Parse timestamps
df_all['UTC'] = pd.to_datetime(df_all['UTC'], utc=True, errors='coerce')
run_hours = 2*(df_all['UTC'].iloc[-1]-df_all['UTC'].iloc[0]).total_seconds()/3600
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
night_df = df_local[(df_local['sunalt']<= -18)]
# Ensure time is sorted
night_df = night_df.sort_values("UTC")

# Calculate differences between consecutive UTC timestamps
dt = night_df["UTC"].diff().dropna()

# Total duration in hours (sum of all intervals)
night_hours = dt.dt.total_seconds().sum() / 3600
pct_night = 100 * night_hours / run_hours if run_hours else 0

summary_html = f"""
<h2>1. Annual Summary Statistics</h2>
<ul>
  <li><b>Site:</b> {site}</li>
  <li><b>Coordinates:</b> {latlonel}</li>
  <li><b>Time Range:</b> {start_str} to {end_str}</li>
  <li><b>Total Run Hours:</b> {run_hours:.1f}</li>
  <li><b>Night Hours (sunalt<-18):</b> {night_hours:.1f}</li>
  <li><b>% Night:</b> {pct_night:.1f}%</li>
</ul>
"""

# Histogram
fig_hist = px.histogram(df_all, x="SQM", nbins=100, title="NSB histogram")
fig_hist.write_image(f"{label}_histogram.png", width=600, height=400)

# Jellyfish
# Create a copy and calculate MST
jelly_df = df_all.copy()
jelly_df['MST'] = jelly_df['UTC'].dt.tz_convert('America/Phoenix')
jelly_df['hour'] = jelly_df['MST'].dt.hour + jelly_df['MST'].dt.minute / 60
jelly_df['hour_shifted'] = jelly_df['hour'].apply(lambda h:
                                                  h if h >= 18 else h + 24)
jelly_df['day'] = jelly_df['MST'].dt.date

# Define bins
x_bins = np.linspace(18, 30, 100)
y_bins = np.linspace(jelly_df['SQM'].min(), jelly_df['SQM'].max(), 150)

# Compute 2D histogram
H, xedges, yedges = np.histogram2d(
    jelly_df['hour_shifted'], jelly_df['SQM'], bins=[x_bins, y_bins]
)

# Apply log scaling to bin counts
z_log = np.log1p(H.T)

# Create plot
fig_jelly = go.Figure(data=go.Heatmap(
    z=z_log,
    x=0.5 * (xedges[:-1] + xedges[1:]),
    y=0.5 * (yedges[:-1] + yedges[1:]),
    colorscale='Hot',
    colorbar=dict(title='log(Count+1)')
))

# Set x-axis ticks from 17 to 7 (mapped to 17–31)
tick_vals = list(range(17, 32))  # 17 to 31 (31 = 7 AM next day)
tick_text = [str(h if h < 24 else h - 24) for h in tick_vals]  #24→0, 25→1 etc.
# Flip the y-axis manually
y_centers = 0.5 * (yedges[:-1] + yedges[1:])
z_log_flipped = z_log[::-1]

fig_jelly = go.Figure(data=go.Heatmap(
    z=z_log_flipped,
    x=0.5 * (xedges[:-1] + xedges[1:]),
    y=y_centers[::-1],  # reversed
    colorscale='Hot',
    colorbar=dict(title='log(Count+1)')
))

fig_jelly.update_layout(
    title="Jellyfish Plot)",
    xaxis_title="Hour (UTC)",
    yaxis_title="NSB (mag/arcsec²)",
    xaxis=dict(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_text
    ),
    plot_bgcolor="#D3D3D3",       # light gray background
    paper_bgcolor="#D3D3D3",      # light gray border area
)
# Save interactive HTML and static PNG
pio.write_html(fig_jelly, file="plot3_jellyfish.html",
               include_plotlyjs='cdn', full_html=False)
fig_jelly.write_image("plot3_jellyfish.png", scale=2, width=1000, height=700)

# --- HEATMAP PLOT (FULL RANGE, MST LOCAL TIME) ---
# Step 1: Prepare data
heatmap_df = df_all.copy()
# Convert UTC to MST
heatmap_df['MST'] = heatmap_df['UTC'].dt.tz_convert('America/Phoenix')
heatmap_df['hour'] = heatmap_df['MST'].dt.hour
heatmap_df['minute'] = heatmap_df['MST'].dt.minute
heatmap_df['date'] = heatmap_df['MST'].dt.date

# Keep only 17h to 7h (next day)
night_mask = (heatmap_df['hour'] >= 17) | (heatmap_df['hour'] < 7)
heatmap_df = heatmap_df[night_mask].copy()

# Shift hours: 0–6 ➝ 24–30, bin by 10 min
heatmap_df['decimal_hour'] = heatmap_df['hour'] + heatmap_df['minute'] / 60
heatmap_df['hour_shifted'] = heatmap_df['decimal_hour'].apply(lambda h: h if h >= 18 else h + 24)
heatmap_df['hour_bin'] = (heatmap_df['hour_shifted'] // (10/60)) * (10/60)
heatmap_df['hour_bin'] = heatmap_df['hour_bin'].round(2)

# Pivot: index = hour_bin, columns = date, values = SQM
pivot = heatmap_df.pivot_table(index='hour_bin', columns='date', values='SQM', aggfunc='mean')
pivot = pivot.sort_index(ascending=False)  # ⬅️ REVERSE y-axis

# Create readable y-ticks: 18–23 and 0–6 (as 24–30)
yticks = []
yticklabels = []
for h in range(18, 24):
    yticks.append(h)
    yticklabels.append(str(h))
for h in range(0, 7):
    yticks.append(h + 24)
    yticklabels.append(str(h))

# Filter yticks present in pivot
yticks_present = [h for h in yticks if h in pivot.index]
ytick_labels_present = [str(h % 24) for h in yticks_present]  # show 0–6 

# Sparse x-ticks (monthly or fallback)
x_dates = pivot.columns
if len(x_dates) > 15:
    xticks = [i for i, d in enumerate(x_dates) if d.day == 1]
    if not xticks:
        xticks = list(range(0, len(x_dates), max(1, len(x_dates)//10)))
else:
    xticks = list(range(len(x_dates)))
xticklabels = [str(x_dates[i]) for i in xticks]

# Plot heatmap
fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(pivot, cmap='inferno', ax=ax, cbar_kws={'label': 'mag/arcsec²'},
            xticklabels=False, yticklabels=False)

ax.set_title("Heatmap, 10-min bins", fontsize=13)
ax.set_xlabel("Date", fontsize=11)
ax.set_ylabel("Hour (MST)", fontsize=11)
ax.set_yticks([pivot.index.get_loc(h) for h in yticks_present])
ax.set_yticklabels(ytick_labels_present, fontsize=8, rotation=0)
ax.set_xticks(xticks)
ax.set_xticklabels(xticklabels, rotation=45, fontsize=7)

plt.tight_layout()
fig.savefig("plot4_heatmap.png", dpi=150)
plt.close(fig)

# HTML wrapper with larger height to avoid scrolling
with open("plot4_heatmap.html", "w") as f:
    f.write("""
<h2>4. Heatmap</h2>
   <img src="plot4_heatmap.png" width="100%" height="1000" alt="Heatmap">
    """)
#
# Chi² histogram
fig_chi2 = px.histogram(df_all, x='chisquared', nbins=100,
                         title="chisquared Histogram")
fig_chi2.write_image(f"{label}_chisq.png", width=600, height=400)
# Save interactive HTML
pio.write_html(fig_hist, file="plot2_histogram.html",
               include_plotlyjs='cdn', full_html=False)
pio.write_html(fig_jelly, file="plot3_jellyfish.html",
               include_plotlyjs='cdn', full_html=False)
pio.write_html(fig_chi2, file="plot5_chi2.html",
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
    <h2>2. Histogram of NSB in mag/arcsec²</h2>
    <iframe src="plot2_histogram.html" width="100%" height="400"></iframe>
    <h2>3. Jellyfish Plot</h2>
    <iframe src="plot3_jellyfish.html" width="100%" height="500"></iframe>
    <h2>4. Heatmap</h2>
    <iframe src="plot4_heatmap.html" width="100%" height="800"></iframe>
    <h2>5. Chi² Histogram</h2>
    <iframe src="plot5_chi2.html" width="100%" height="400"></iframe>
</body>
</html>
""")
status = {
    "status": "✅ Plots ready",
    "html": f"{label}.analysis.html"
}

with open("status.json", "w") as f:
    json.dump(status, f)

print(f"✅ Wrote status.json for {label}")
