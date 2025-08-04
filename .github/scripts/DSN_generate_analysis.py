import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
import argparse
import json

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

# Plot 1: Histogram of SQM
fig1 = px.histogram(df_all, x='SQM', nbins=60, title='Histogram of SQM')
pio.write_html(fig1, file=f"{label}_histogram.html", auto_open=False)
fig1.write_image(f"{label}_histogram.png")

# Plot 2: Heatmap by hour and day
if 'UTC' in df_all.columns and 'SQM' in df_all.columns:
    df_all['hour'] = df_all['UTC'].dt.hour
    df_all['date'] = df_all['UTC'].dt.date
    heatmap_data = df_all.pivot_table(index='hour', columns='date', values='SQM', aggfunc='mean')
    fig2 = px.imshow(heatmap_data, labels=dict(x="Date", y="Hour", color="Mean SQM"),
                     title="Heatmap of Mean SQM by Hour and Date")
    pio.write_html(fig2, file=f"{label}_heatmap.html", auto_open=False)
    fig2.write_image(f"{label}_heatmap.png")

# Plot 3: Jellyfish
if 'UTC' in df_all.columns and 'SQM' in df_all.columns:
    df_all['hour_float'] = df_all['UTC'].dt.hour + df_all['UTC'].dt.minute / 60.0
    df_all['mag_bin'] = pd.cut(df_all['SQM'], bins=np.arange(10, 25.25, 0.25))
    df_all['hour_bin'] = pd.cut(df_all['hour_float'], bins=np.arange(0, 24.25, 0.25))
    jelly_counts = df_all.groupby(['hour_bin', 'mag_bin']).size().unstack(fill_value=0)
    z = np.log1p(jelly_counts.values.T)
    x_labels = [str(int(b.left)) for b in jelly_counts.index.categories]
    y_labels = [str(round(b.left, 2)) for b in jelly_counts.columns.categories]
    fig3 = go.Figure(data=go.Heatmap(
        z=z[::-1],
        x=x_labels,
        y=y_labels[::-1],
        colorscale='Hot',
        colorbar=dict(title='log(Count+1)')
    ))
    fig3.update_layout(
        title='Jellyfish Plot: SQM vs Hour of Night',
        xaxis_title='Hour of Night',
        yaxis_title='SQM',
        plot_bgcolor='lightgray'
    )
    pio.write_html(fig3, file=f"{label}_jellyfish.html", auto_open=False)
    fig3.write_image(f"{label}_jellyfish.png")

# Plot 4: Chi-squared Histogram
if 'chisquared' in df_all.columns:
    fig4 = px.histogram(df_all, x='chisquared', nbins=50, title='Histogram of Chi-squared')
    pio.write_html(fig4, file=f"{label}_chisq.html", auto_open=False)
    fig4.write_image(f"{label}_chisq.png")

# Generate main dashboard HTML
html_files = [f for f in os.listdir('.') if f.startswith(label) and f.endswith('.html')]
html_links = '\n'.join([f'<li><a href="{f}">{f}</a></li>' for f in html_files])
main_html = f"""
<html>
  <head><title>{label} Analysis</title></head>
  <body>
    <h1>Analysis for {label}</h1>
    <ul>
      {html_links}
    </ul>
  </body>
</html>
"""

with open(f"{label}.analysis.html", 'w') as f:
    f.write(main_html)

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
