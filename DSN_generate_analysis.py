import os
import shutil
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
import argparse
import json
import glob
import datetime
from pathlib import Path
#
parser = argparse.ArgumentParser()
parser.add_argument('--input_dir', required=True)
parser.add_argument('--from', dest='from_time', required=True)
parser.add_argument('--to', dest='to_time', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()

in_dir = args.input_dir
label = args.label
start_time = pd.to_datetime(args.from_time, utc=True)
end_time = pd.to_datetime(args.to_time, utc=True)
start_str = start_time.strftime("%y-%m-%d %H:%M:%S")
end_str = end_time.strftime("%y-%m-%d %H:%M:%S")
#
outdir = Path("analysis") / label
outdir.mkdir(parents=True, exist_ok=True)
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

print(f"📁 Reading from {in_dir} for label {label}")
all_files = [f for f in os.listdir(in_dir) if f.startswith(label) and f.endswith('.csv')]
if not all_files:
    raise FileNotFoundError(f"No files matching {label}_*.csv found in {in_dir}")

print(f"📄 Found {len(all_files)} files: {all_files}")

df_list = []
for file in all_files:
    filepath = os.path.join(in_dir, file)
    try:
        df = pd.read_csv(filepath, comment='#', sep=None, engine='python')
        df['sourcefile'] = file
        df_list.append(df)
    except Exception as e:
        print(f"⚠️ Skipping {file}: {e}")

df_all = pd.concat(df_list)

if 'UTC' in df_all.columns:
    df_all['UTC'] = pd.to_datetime(df_all['UTC'], utc=True, errors='coerce')
    df_all = df_all.dropna(subset=['UTC'])
    df_all = df_all[(df_all['UTC'] >= start_time) & (df_all['UTC'] <= end_time)]
else:
    raise ValueError("Missing UTC column")

# Stats
print(f"✅ Filtered to {len(df_all)} records in time range")
run_hours = (df_all['UTC'].iloc[-1]-df_all['UTC'].iloc[0]).total_seconds()/3600
#
df_local = df_all.copy()
df_local['Local'] = df_local['UTC'].dt.tz_convert('America/Phoenix')
df_local['Date'] = df_local['Local'].dt.date
# Calculate differences between consecutive UTC timestamps
night_df = df_local[(df_local['sunalt']<= -18)]
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
  <li><b>Total Run Hours (18-6h):</b> {run_hours:.1f}</li>
  <li><b>Night Hours (sunalt<-18):</b> {night_hours:.1f}</li>
  <li><b>% Night:</b> {pct_night:.1f}%</li>
</ul>
<h2>2. Night Sky Brightness (NSB)</h2>
"""
# set plot sizes
plot_w=700
plot_h=400
# Plot 1: Histogram of NSB
fig1 = px.histogram(df_all, x='SQM', nbins=60, title='NSB (mag/arcsec²) Histogram')
fig1.update_layout(
    title_font=dict(size=24),  # Larger title
    title_x=0.5,               # Center title
    width=plot_w,
    height=plot_h
)
pio.write_html(fig1, file=str(outdir / f"{label}_histogram.html"),
               auto_open=False)
fig1.write_image(str(outdir / f"{label}_histogram.png"))

# Plot 2: Heatmap by hour and day
if 'UTC' in df_all.columns and 'SQM' in df_all.columns:
    df_all['hour'] = df_all['UTC'].dt.hour
    df_all['date'] = df_all['UTC'].dt.date
    heatmap_data = df_all.pivot_table(index='hour', columns='date', values='SQM', aggfunc='mean')
    fig2 = px.imshow(heatmap_data, labels=dict(x="Date", y="Hour", color="Mean NSB"),
                     title="NSB (mag/arcsec²) Heatmap")
    fig2.update_layout(
        title_font=dict(size=24),  # Larger title
        title_x=0.5,               # Center title
        width=plot_w,
        height=plot_h
    )
    pio.write_html(fig2, file=str(outdir / f"{label}_heatmap.html"),
               auto_open=False)
    fig2.write_image(str(outdir / f"{label}_heatmap.png"))

# --- Jellyfish Plot (fig3): hour wrap 17→23 then 0→7, log contrast ---

# Ensure hour and SQM are clean
h = df_all["hour"].astype(int).clip(0, 23)
y = pd.to_numeric(df_all["SQM"], errors="coerce")

# Bins
x_bins = np.arange(-0.5, 24.5, 1)                      # 24 hour bins
ymin  = np.nanpercentile(y, 0.5) if np.isfinite(y).any() else 16
ymax  = np.nanpercentile(y, 99.5) if np.isfinite(y).any() else 22
y_bins = np.linspace(max(16, ymin), min(22, ymax), 60) # 60 y-bins within a sane range

# 2D histogram (shape: 24 x Ny)
hist, xedges, yedges = np.histogram2d(h, y, bins=[x_bins, y_bins])

# Log contrast
hist_log = np.log10(hist + 1.0)

# Desired X order: 17..23, 0..7  (15 columns)
hour_order = list(range(17, 24)) + list(range(0, 8))
# Reorder columns to match desired hour sequence
hist_log_sel = hist_log[hour_order, :]                 # (15, Ny)

# Axes
x_vals    = hour_order
tickvals  = hour_order
ticktext  = [str(hh) for hh in hour_order]
y_centers = 0.5 * (yedges[:-1] + yedges[1:])

# Heatmap (note .T so Z is Ny x 15 = y by x)
fig3 = go.Figure(data=go.Heatmap(
    z=hist_log_sel.T,
    x=x_vals,
    y=y_centers,
    colorscale="Viridis",
    colorbar=dict(title="log₁₀ density"),
    zmin=0  # 0 -> no counts (dark); remove if you prefer autoscale
))

fig3.update_layout(
    title="Jellyfish Plot",
    title_x=0.5,                      # center title
    xaxis=dict(
        title="Hour (MST)",
        tickmode="array",
        tickvals=tickvals,
        ticktext=ticktext
    ),
    yaxis=dict(title="NSB mag/arcsec²")
)

# Save
pio.write_html(fig3, file=str(outdir / f"{label}_jellyfish.html"),
               auto_open=False)
fig3.write_image(str(outdir / f"{label}_jellyfish.png")))

# Plot 4: Chi-squared Histogram
if 'chisquared' in df_all.columns:
    fig4 = px.histogram(df_all, x='chisquared', nbins=50, title='Chi² (cloudyness) Histogram')
    fig4.update_layout(
        title_font=dict(size=24),  # Larger title
        title_x=0.5,               # Center title
        width=plot_w,
        height=plot_h
    )

    pio.write_html(fig4, file=str(outdir / f"{label}_chisq.html"),
               auto_open=False)
    fig4.write_image(str(outdir / f"{label}_chisq.png"))

# Generate main dashboard HTML
main_html = f"<html><head><title>{label} Analysis</title></head><body>\n"
main_html += f"<h1>{label} Analysis</h1>\n"
timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
main_html += f"<p style='font-size:small'>Generated: {timestamp}</p>\n"
main_html += summary_html +"\n"  # 👈 Include site summary

for plot_type in ["histogram", "heatmap", "jellyfish", "chisq"]:
    html_file = f"analysis/{label}/{label}_{plot_type}.html"
    if os.path.exists(html_file):
        with open(html_file) as f:
            main_html += f.read() + "\n"
    else:
        main_html += f"<p>⚠️ Missing {plot_type} plot.</p>\n"

main_html += "</body></html>"

# Generate main HTML wrapper
output_path = outdir / f"{label}.analysis.html"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(main_html)
print(f"✅ Wrote main HTML to {output_path}")
existing = glob.glob(f"analysis/{label}/{label}_*.html")
print(f"🧾 Found {len(existing)} individual plot HTML files: {existing}")
# don't write status-{label}.json here
