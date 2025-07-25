#!/usr/bin/env python3
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import base64
import os
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument('--input_dir', required=True, help='Directory containing Box-downloaded CSV files')
parser.add_argument('--from', dest='from_time', required=True, help='Start UTC timestamp (e.g., 2025-07-01T00:00:00Z)')
parser.add_argument('--to', dest='to_time', required=True, help='End UTC timestamp (e.g., 2025-07-10T00:00:00Z)')
parser.add_argument('--label', required=True, help='Site label (e.g., DSN021-S)')
parser.add_argument('--output', default='dashboard.html', help='Output HTML file')
args = parser.parse_args()

start_time = pd.to_datetime(args.from_time)
end_time = pd.to_datetime(args.to_time)
label = args.label
indir = args.input_dir

# Find all matching CSVs
csv_files = sorted([f for f in os.listdir(indir) if f.startswith(label) and f.endswith('.csv')])
if not csv_files:
    raise FileNotFoundError(f"No files found starting with {label} in {indir}")

# Load and combine data
dfs = []
for fname in csv_files:
#    print(fname)
    path = os.path.join(indir, fname)
    sep = ';' if label.endswith('T') else ','
    df = pd.read_csv(path, sep=sep, header=None, skiprows=1,comment='#')
#    print(df.head())
    df.columns = ['UTC','SQM','lum','chisquared','moonalt','LST','sunalt']
#    df.columns = ['UTC', 'LOCAL', 'TEMP', 'COUNT', 'FREQ', 'MSAS']
    df['UTC'] = pd.to_datetime(df['UTC'], errors='coerce')
    df = df[(df['UTC'] >= start_time) & (df['UTC'] <= end_time)]
    dfs.append(df)

data = pd.concat(dfs)
if data.empty:
    raise ValueError("No data in selected time range.")

# Utility to render figure to base64 <img>
def fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

# Plot 1: Brightness vs time
fig1, ax1 = plt.subplots(figsize=(10, 4))
ax1.plot(data['UTC'], data['SQM'], '.', markersize=2)
ax1.invert_yaxis()
ax1.set_title('Sky Brightness Over Time')
ax1.set_ylabel('mag/arcsec²')
ax1.set_xlabel('UTC')
img1 = fig_to_base64(fig1)

# Plot 2: Histogram
fig2, ax2 = plt.subplots()
data['SQM'].hist(ax=ax2, bins=30)
ax2.set_title('Histogram of SQM')
img2 = fig_to_base64(fig2)

# Plot 3: Jellyfish (MSAS vs Count)
fig3, ax3 = plt.subplots()
sc = ax3.scatter(data['UTC'], data['SQM'], c=data['SQM'], cmap='viridis', s=3)
ax3.set_title('Jellyfish Plot (Counts vs Time)')
fig3.colorbar(sc, ax=ax3, label='MSAS')
img3 = fig_to_base64(fig3)

# Plot 4: Heatmap by hour and date
data['DATE'] = data['UTC'].dt.date
data['HOUR'] = data['UTC'].dt.hour
pivot = data.pivot_table(index='HOUR', columns='DATE', values='SQM', aggfunc='mean')
fig4, ax4 = plt.subplots(figsize=(12, 5))
sns.heatmap(pivot, ax=ax4, cmap='mako_r')
ax4.set_title('Heatmap of MSAS by Hour and Date')
img4 = fig_to_base64(fig4)

# Plot 5: Sigma Histogram
mu, sigma = data['SQM'].mean(), data['SQM'].std()
fig5, ax5 = plt.subplots()
data['SQM'].hist(ax=ax5, bins=40, alpha=0.7)
for i in range(1, 4):
    ax5.axvline(mu + i * sigma, color='red', linestyle='--')
    ax5.axvline(mu - i * sigma, color='red', linestyle='--')
ax5.set_title('Sigma Histogram of MSAS')
img5 = fig_to_base64(fig5)

# Generate dashboard HTML
html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{label} – Southern Arizona Dark Sky Network</title>
    <meta charset="utf-8"/>
    <style>body {{ font-family: sans-serif; max-width: 1000px; margin: auto; }}</style>
</head>
<body>
    <h1>{label} — Southern Arizona Dark Sky Network</h1>
    <p><b>Time range:</b> {start_time} to {end_time}</p>
    <h2>1. Brightness Over Time</h2>
    <img src="data:image/png;base64,{img1}"/>
    <h2>2. Histogram of MSAS</h2>
    <img src="data:image/png;base64,{img2}"/>
    <h2>3. Jellyfish Plot</h2>
    <img src="data:image/png;base64,{img3}"/>
    <h2>4. Heatmap of MSAS by Hour and Date</h2>
    <img src="data:image/png;base64,{img4}"/>
    <h2>5. Sigma Histogram</h2>
    <img src="data:image/png;base64,{img5}"/>
</body>
</html>
"""

with open(args.output, "w") as f:
    f.write(html)
print(f"✅ Dashboard written to {args.output}")
