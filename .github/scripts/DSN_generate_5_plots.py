#!/usr/bin/env python3
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import base64
import os
from datetime import datetime, timedelta

parser = argparse.ArgumentParser()
parser.add_argument('--input_dir', required=True)
parser.add_argument('--from', dest='from_time', required=True)
parser.add_argument('--to', dest='to_time', required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--output', default='dashboard.html')
args = parser.parse_args()

start_time = pd.to_datetime(args.from_time, utc=True)
end_time = pd.to_datetime(args.to_time, utc=True)
label = args.label
indir = args.input_dir

if not os.path.isdir(indir):
    print(f"⚠️  Warning: input_dir '{indir}' does not exist. Skipping.")
    exit(0)

csv_files = sorted([f for f in os.listdir(indir) if f.startswith(label) and f.endswith('.csv')])
if not csv_files:
    print(f"⚠️  Warning: No CSV files found for label '{label}' in directory '{indir}'")
    exit(0)

dfs = []
for fname in csv_files:
    path = os.path.join(indir, fname)
    sep = ';' if label.endswith('T') else ','
    df = pd.read_csv(path, sep=sep, comment='#')
    df['UTC'] = pd.to_datetime(df['UTC'], utc=True, errors='coerce')
    if df.columns[0].strip() == 'UTC':
        df.columns = df.columns.str.strip()
    else:
        df.columns = ['UTC', 'SQM', 'lum', 'chisquared', 'moonalt', 'LST', 'sunalt']
    df['UTC'] = pd.to_datetime(df['UTC'], format='%Y-%m-%dT%H:%M:%SZ', utc=True, errors='coerce')
    df = df[(df['UTC'] >= start_time) & (df['UTC'] <= end_time)]
    dfs.append(df)

if not dfs:
    print("⚠️  No data matched time range.")
    exit(0)

data = pd.concat(dfs, ignore_index=True)
data = data.dropna(subset=['UTC', 'SQM'])

def fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

# 1. Brightness over time
fig1, ax1 = plt.subplots(figsize=(10, 4))
ax1.plot(data['UTC'], data['SQM'], '.', markersize=2)
ax1.invert_yaxis()
ax1.set_title('Sky Brightness Over Time')
ax1.set_ylabel('mag/arcsec²')
ax1.set_xlabel('UTC')
img1 = fig_to_base64(fig1)

# 2. Histogram
fig2, ax2 = plt.subplots()
data['SQM'].hist(ax=ax2, bins=30)
ax2.set_title('Histogram of SQM')
img2 = fig_to_base64(fig2)

# 3. Jellyfish as 2D histogram
data['date'] = data['UTC'].dt.floor('D')
data['midnight'] = pd.to_datetime(data['date'], utc=True) + pd.Timedelta(hours=12)
data['hours_from_midnight'] = (data['UTC'] - data['midnight']).dt.total_seconds() / 3600
data = data.dropna(subset=['hours_from_midnight', 'SQM'])

fig3, ax3 = plt.subplots(figsize=(10, 4))
hb = ax3.hist2d(
    data['hours_from_midnight'].astype(float),
    data['SQM'].astype(float),
    bins=[100, 100],
    cmap='viridis'
)
ax3.set_title('Jellyfish: Density of Sky Brightness vs Time from Midnight')
ax3.set_xlabel('Hours from Midnight (UTC)')
ax3.set_ylabel('SQM (mag/arcsec²)')
ax3.invert_yaxis()
fig3.colorbar(hb[3], ax=ax3, label='Counts')
img3 = fig_to_base64(fig3)

# 4. Heatmap
data['HOUR'] = data['UTC'].dt.hour
pivot = data.pivot_table(index='HOUR', columns='date', values='SQM', aggfunc='mean')
fig4, ax4 = plt.subplots(figsize=(12, 5))
sns.heatmap(pivot, ax=ax4, cmap='mako_r')
ax4.set_title('Heatmap of SQM by Hour and Date')
img4 = fig_to_base64(fig4)

# 5. Sigma Histogram
mu, sigma = data['SQM'].mean(), data['SQM'].std()
fig5, ax5 = plt.subplots()
data['SQM'].hist(ax=ax5, bins=40, alpha=0.7)
for i in range(1, 4):
    ax5.axvline(mu + i * sigma, color='red', linestyle='--')
    ax5.axvline(mu - i * sigma, color='red', linestyle='--')
ax5.set_title('Sigma Histogram of SQM')
img5 = fig_to_base64(fig5)

# HTML dashboard output
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
    <h2>2. Histogram of SQM</h2>
    <img src="data:image/png;base64,{img2}"/>
    <h2>3. Jellyfish Density Plot</h2>
    <img src="data:image/png;base64,{img3}"/>
    <h2>4. Heatmap of SQM by Hour and Date</h2>
    <img src="data:image/png;base64,{img4}"/>
    <h2>5. Sigma Histogram</h2>
    <img src="data:image/png;base64,{img5}"/>
</body>
</html>
"""

with open(args.output, "w") as f:
    f.write(html)
print(f"✅ Dashboard written to {args.output}")
