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
count_le_0009 = (night_df['chisquared'] <= 0.009).sum()
total = len(night_df['chisquared'])
percent_le_0009 = 100 * count_le_0009 / total

summary_html = f"""
<h2>1. Annual Summary Statistics</h2>
<ul>
  <li><b>Site:</b> {site}</li>
  <li><b>Coordinates:</b> {latlonel}</li>
  <li><b>Time Range:</b> {start_str} to {end_str}</li>
  <li><b>Total Run Hours (18-6h):</b> {run_hours:.1f}</li>
  <li><b>Night Hours (sunalt<-18):</b> {night_hours:.1f}</li>
  <li><b>Run Hours:</b> {pct_night:.1f}%</li>
  <li><b>Run Hours w/o clouds:</b> {percent_le_0009:.1f}%</li>
</ul>
<h2>2. Night Sky Brightness (NSB) plots (interactive)</h2>
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

# For both heatmap and jellyfish
# Parse UTC timestamps, always tz-aware
ts_utc = pd.to_datetime(df_all["UTC"], errors="coerce", utc=True)
# Convert to MST. Fallback to UTC-7 if tz db unavailable.
ts_mst = ts_utc - pd.Timedelta(hours=7)
# Fractional hour in MST (includes minutes/seconds)
hour_frac = (
    ts_mst.dt.hour.astype(float)
    + ts_mst.dt.minute.astype(float) / 60.0
    + ts_mst.dt.second.astype(float) / 3600.0
).to_numpy() % 24.0
# Plot 2: Heatmap by 15-min bin (wrapped 18:00→06:00)
if 'UTC' in df_all.columns and 'SQM' in df_all.columns:
    # 15-min bins → indices 0..95
    bin_size = 0.25  # hours
    bin_idx = np.floor(hour_frac / bin_size).astype(int).clip(0, 95)

    # Wrap: 18:00–23:45 (72..95), then 00:00–05:45 (0..23) → total 48 bins
    start_idx = int(18 / bin_size)  # 72
    end_idx   = int(6  / bin_size)  # 24
    order = list(range(start_idx, 96)) + list(range(0, end_idx))  # length 48

    # Keep only bins in that night window
    sel_mask = (bin_idx >= start_idx) | (bin_idx < end_idx)
    df_sel = df_all.loc[sel_mask].copy()
    ts_sel = ts_mst.loc[sel_mask]
    bins_sel = bin_idx[sel_mask]

    # Wrapped compact positions 0..47
    wrapped_pos = np.where(bins_sel >= start_idx, bins_sel - start_idx, bins_sel + (96 - start_idx))
    df_sel['date'] = ts_sel.dt.date
    df_sel['bin_pos'] = wrapped_pos
    df_sel['SQM_num'] = pd.to_numeric(df_sel['SQM'], errors='coerce')

    # Pivot to (y=bin_pos 0..47, x=date), mean SQM
    heat = df_sel.pivot_table(index='bin_pos', columns='date', values='SQM_num', aggfunc='mean')
    heat = heat.reindex(range(0, 48), axis=0)

    # Y tick labels every hour (4 bins)
    x_edges = np.linspace(0, 24, 97)  # exact edges for 15-min bins
    hour_vals_for_row = [x_edges[order[i]] % 24 for i in range(48)]
    tickvals = list(range(0, 48, 4))  # every hour
    ticktext = [str(int(hour_vals_for_row[i])) for i in tickvals]
    # Get z values
    z_values = heat.values
    z_min, z_max = np.nanmin(z_values), np.nanmax(z_values)
    den = (z_max - z_min) if np.isfinite(z_max - z_min) and \
        (z_max - z_min) != 0 else 1.0
    z_norm  = (z_values - z_min) / den
    gamma   = 0.4
    z_gamma = np.clip(z_norm, 0, 1) ** gamma

    fig2 = go.Figure(data=go.Heatmap(
        z=z_gamma,                     # for colors (gamma-stretched)
        customdata=z_values,           # keep raw values here
        hovertemplate="NSB: %{customdata:.1f} mag/arcsec²<extra></extra>",
        x=[str(c) for c in heat.columns],
        y=np.arange(z_gamma.shape[0]),
        colorscale="Turbo",
        colorbar=dict(title="Mean NSB", thickness=12)
    ))
    fig2.update_layout(
        title="NSB (mag/arcsec²) Heatmap",
        title_font=dict(size=24),
        title_x=0.5,
        xaxis=dict(title="Date"),
        yaxis=dict(
            title="Hour (MST)",
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext
        ),
        width=plot_w,
        height=plot_h
    )

    pio.write_html(fig2, file=str(outdir / f"{label}_heatmap.html"),
                   auto_open=False)
    fig2.write_image(str(outdir / f"{label}_heatmap.png"))
#    
# --- Jellyfish (15-min bins from UTC → MST, wrapped night) ---
# Wrap order: 17:00–23:45, then 00:00–07:45  (no x gap by using a compact index)
start_idx = int(17 / 0.25)  # 68
end_idx   = int(8 / 0.25)   # 32
order = list(range(start_idx, len(x_edges) - 1)) + list(range(0, end_idx))
# Put ticks every hour (4 bins apart) with MST hour labels
tickvals = list(range(0, len(order), 4))

# Y values
y = pd.to_numeric(df_all["SQM"], errors="coerce").to_numpy()

# 15-min bins
x_edges = np.arange(0.0, 24.0001, 0.25)   # 0, 0.25, ..., 24.0
order = list(range(start_idx, len(x_edges) - 1)) + list(range(0, end_idx))
# Robust Y range
ymin = np.nanpercentile(y, 0.5) if np.isfinite(y).any() else 16
ymax = np.nanpercentile(y, 99.5) if np.isfinite(y).any() else 22
y_edges = np.linspace(max(10, ymin), min(24.5, ymax), 100)

# 2D histogram and log contrast
H, _, _ = np.histogram2d(hour_frac, y, bins=[x_edges, y_edges])
Hlog = np.log10(H + 1.0)

Z = Hlog[order, :]                 # (Nx, Ny)
x_compact = np.arange(len(order))  # 0..59 (15*4 bins)
# Put ticks every hour (4 bins apart) with MST hour labels
tickvals = list(range(0, len(order), 4))
ticktext = [str(int(x_edges[order[i]] % 24)) for i in tickvals]
y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])

fig3 = go.Figure(go.Heatmap(
    z=Z.T,
    x=x_compact,
    y=y_centers,
    colorscale="Turbo",      # better than Viridis
    colorbar=dict(title="log₁₀ density")
))
fig3.update_layout(
    title="Jellyfish Plot",
    title_font=dict(size=24),  # Larger title
    title_x=0.5,
    xaxis=dict(title="Hour (MST)", tickmode="array", tickvals=tickvals,
               ticktext=ticktext),
    yaxis=dict(title="NSB mag/arcsec²"),
    width=plot_w, height=plot_h
)

# Save
pio.write_html(fig3, file=str(outdir / f"{label}_jellyfish.html"),
               auto_open=False)
fig3.write_image(str(outdir / f"{label}_jellyfish.png"))

# Plot 4: Chi-squared Histogram (cap at 1.0; overflow -> last bin)
if 'chisquared' in df_all.columns:
    s = pd.to_numeric(df_all['chisquared'], errors='coerce')

    # Count overflow, then cap to 1.0 (put all >1 into last bin)
    overflow = (s > 1.0).sum()
    s_cap = s.clip(upper=1.0)

    # Optional: nudge exact 1.0 to ensure it lands inside the last bin if your
    # plotting lib treats the right edge as open; comment out if not needed.
    # s_cap = np.where(s_cap >= 1.0, np.nextafter(1.0, 0.0), s_cap)

    fig4 = go.Figure(go.Histogram(
        x=s_cap,
        nbinsx=100,
        xbins=dict(start=0.0, end=1.0),  # explicit 0..1 range
        marker=dict(color="#4e79a7"),
        hovertemplate="χ²: %{x:.4f}<br>count: %{y}<extra></extra>"
    ))

    # Red reference line at 0.009
    fig4.add_vline(
        x=0.009, line_width=2, line_dash="dash", line_color="red",
        annotation_text="0.009", annotation_position="top right"
    )

    # Show overflow count (how many were >1 and thus added into the 1.0 bin)
    fig4.add_annotation(
        x=0.995, y=1, xref="x", yref="paper",
        xanchor="right", yanchor="top",
        text=f"overflow (χ²>1): {int(overflow)}",
        showarrow=False, font=dict(size=12, color="#444"), bgcolor="rgba(255,255,255,0.6)"
    )

    fig4.update_layout(
        title="χ² Histogram (0–1; >1 in last bin)",
        title_x=0.5,
        bargap=0.02,
        xaxis=dict(title="χ²", range=[0, 1]),
        yaxis=dict(title="Count"),
        width=plot_w, height=plot_h
    )

    pio.write_html(fig4, file=str(outdir / f"{label}_chisq.html"),
                   auto_open=False)
    fig4.write_image(str(outdir / f"{label}_chisq.png"))
#
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
