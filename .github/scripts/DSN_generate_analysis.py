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

os.makedirs("public", exist_ok=True)
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
    latlonel='Lon '+str(lon)+' Lat '+str(lat)+' El '+str(el)+' m'    latlonel='Lon '+str(lon)+' Lat '+str(lat)+' El '+str(el)+' m'
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

print(f"✅ Filtered to {len(df_all)} records in time range")
run_hours = (df_all['UTC'].iloc[-1]-df_all['UTC'].iloc[0]).total_seconds()/3600

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
  <li><b>Total Run Hours (18-6h):</b> {run_hours:.1f}</li>
  <li><b>Night Hours (sunalt<-18):</b> {night_hours:.1f}</li>
  <li><b>% Night:</b> {pct_night:.1f}%</li>
</ul>
"""

# Plot 1: Histogram of NSB
fig1 = px.histogram(df_all, x='SQM', nbins=60, title='Histogram of NSB')
fig1.update_layout(
    title_font=dict(size=24),  # Larger title
    width=700,
    height=400
)
pio.write_html(fig1, file=f"public/{label}_histogram.html", auto_open=False)
fig1.write_image(f"public/{label}_histogram.png")

# Plot 2: Heatmap by hour and day
if 'UTC' in df_all.columns and 'SQM' in df_all.columns:
    df_all['hour'] = df_all['UTC'].dt.hour
    df_all['date'] = df_all['UTC'].dt.date
    heatmap_data = df_all.pivot_table(index='hour', columns='date', values='SQM', aggfunc='mean')
    fig2 = px.imshow(heatmap_data, labels=dict(x="Date", y="Hour", color="Mean SQM"),
                     title="Heatmap of Mean SQM by Hour and Date")
    fig2.update_layout(
        title_font=dict(size=24),  # Larger title
        width=700,
        height=400
    )
    pio.write_html(fig2, file=f"public/{label}_heatmap.html", auto_open=False)
    fig2.write_image(f"public/{label}_heatmap.png")

# Plot 3: Jellyfish
if 'UTC' in df_all.columns and 'SQM' in df_all.columns:
    df_all['hour_float'] = df_all['UTC'].dt.hour + df_all['UTC'].dt.minute / 60.0
    df_all['mag_bin'] = pd.cut(df_all['SQM'], bins=np.arange(10, 25.25, 0.25))
    df_all['hour_bin'] = pd.cut(df_all['hour_float'], bins=np.arange(0, 24.25, 0.25))
    jelly_counts = df_all.groupby(['hour_bin', 'mag_bin']).size().unstack(fill_value=0)
    z = np.log1p(jelly_counts.values.T)
    x_labels = [str(int(b.left)) for b in jelly_counts.index.categories]
    y_labels = [str(round(b.left, 2)) for b in jelly_counts.columns.categories]
    fig3 = go.Figure(data=go.Histogram2d(
        x=df["hour"], 
        y=df["SQM"], 
        nbinsx=24, 
        nbinsy=40,
        colorscale="Viridis",        # Use Viridis colormap
        zmin=0,                      # Normalize color scale: min count
        zmax=df["hour"].value_counts().max(),  # Normalize color scale: max count
        colorbar=dict(title="Density")
    ))
     fig3.update_layout(
        title="Jellyfish Plot",
        title_font=dict(size=24),
        width=700,
        height=400,
        yaxis=dict(
            autorange="reversed",
            tickmode='array',
            tickvals=[x * 0.5 for x in range(10, 20)],  # 5.0 to 10.0 mags
            ticktext=[f"{x:.1f}" for x in [x * 0.5 for x in range(10, 20)]],
            title="SQM (mag/arcsec²)"
        ),
        xaxis=dict(
            title="Hour (LST)",
            tickmode="array",
            tickvals=list(range(17, 24)) + list(range(0, 8)),
            ticktext=[str(h) for h in range(17, 24)] + [str(h) for h in range(0, 8)]
        ),
        coloraxis_colorbar=dict(title="Density", ticks="outside")
    )
    pio.write_html(fig3, file=f"public/{label}_jellyfish.html", auto_open=False)
    fig3.write_image(f"public/{label}_jellyfish.png")

# Plot 4: Chi-squared Histogram
if 'chisquared' in df_all.columns:
    fig4 = px.histogram(df_all, x='chisquared', nbins=50, title='Histogram of Chi-squared')
    fig4.update_layout(
        title_font=dict(size=24),  # Larger title
        width=700,
        height=400
    )
    pio.write_html(fig4, file=f"public/{label}_chisq.html", auto_open=False)
    fig4.write_image(f"public/{label}_chisq.png")

# Generate main dashboard HTML
main_html = f"<html><head><title>{label} Analysis</title></head><body>\n"
main_html += f"<h1>{label} Analysis</h1>\n"
main_html += summary_html +"\n"  # 👈 Include site summary

for plot_type in ["histogram", "heatmap", "jellyfish", "chisq"]:
    html_file = f"public/{label}_{plot_type}.html"
    if os.path.exists(html_file):
        with open(html_file) as f:
            main_html += f.read() + "\n"
    else:
        main_html += f"<p>⚠️ Missing {plot_type} plot.</p>\n"

main_html += "</body></html>"

# Generate main HTML wrapper
output_path = f"public/{label}.analysis.html"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

existing = glob.glob(f"public/{label}_*.html")
print(f"🧾 Found {len(existing)} individual plot HTML files: {existing}")
with open(output_path, "w") as f:
    f.write(main_html)
print(f"✅ Wrote main HTML to {output_path}")

# Write status file
status = {
    "status": "✅ Plots ready",
    "html": f"analysis/{label}/{label}.analysis.html"
}

status_path = f"public/status/status-{label}.json"
os.makedirs(os.path.dirname(status_path), exist_ok=True)

with open(status_path, "w") as f:
    json.dump(status, f)

print(f"✅ Wrote status JSON to {status_path}")
# Copy to tmp for later GH Pages step
shutil.copy(status_path, f"/tmp/status-{label}.json")
print(f"✅ Also copied status to /tmp/status-{label}.json")
