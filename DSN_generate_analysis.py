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
def gap_corrected_hours(df, ts_col="UTC", q=10, tol=1.25):
    """
    Sum only 'continuous' intervals:
      - Estimate cadence as the q-th percentile of positive diffs (sec)
      - Keep diffs in (0, cadence*tol]
      - Robust fallbacks if cadence is 0/NaN
    Returns hours (float).
    """
    if df.empty:
        return 0.0

    t = pd.to_datetime(df[ts_col], errors="coerce", utc=True).sort_values()
    t = t[t.notna()]
    if len(t) < 2:
        return 0.0

    diffs = t.diff().dt.total_seconds().to_numpy()[1:]  # skip first NaN
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if diffs.size == 0:
        return 0.0

    # cadence estimate: small-but-robust
    cadence = np.percentile(diffs, q)
    if not np.isfinite(cadence) or cadence <= 0:
        cadence = np.min(diffs)  # fallback
    if not np.isfinite(cadence) or cadence <= 0:
        return 0.0

    max_allowed = cadence * tol
    keep = diffs[(diffs > 0) & (diffs <= max_allowed)]
    seconds = keep.sum()

    # last-ditch fallback: if still zero but we do have diffs, clip at 95th pct
    if seconds == 0 and diffs.size > 0:
        cap = np.percentile(diffs, 95)
        seconds = diffs[diffs <= cap].sum()

    return seconds / 3600.0
#
def _filtered_sqm(df, moon_thr=-10.0, chi_thr=0.009):
    """Return a copy of df filtered to good SQM rows:
       moonalt <= moon_thr AND chisquared <= chi_thr.
       Ensures SQM is numeric and drops NaNs.
    """
    if 'SQM' not in df.columns:
        return df.iloc[0:0].copy()  # empty, SQM missing

    m = pd.Series(True, index=df.index)

    if 'moonalt' in df.columns:
        m &= pd.to_numeric(df['moonalt'], errors='coerce') <= float(moon_thr)
    else:
        m &= False  # no moonalt -> nothing passes

    if 'chisquared' in df.columns:
        m &= pd.to_numeric(df['chisquared'], errors='coerce') <= float(chi_thr)
    else:
        m &= False  # no chisquared -> nothing passes

    out = df.loc[m].copy()
    out['SQM'] = pd.to_numeric(out['SQM'], errors='coerce')
    out = out.dropna(subset=['SQM'])
    return out
#
df_local = df_all.copy()
df_local['Local'] = df_local['UTC'].dt.tz_convert('America/Phoenix')
df_local['Date'] = df_local['Local'].dt.date
# Total (gap-aware)
run_hours = gap_corrected_hours(df_all, ts_col="UTC")
# Night only (sunalt <= -18)
night_df = df_local[df_local["sunalt"] <= -18]
night_hours = gap_corrected_hours(night_df, ts_col="UTC")
#run_hours = (df_all['UTC'].iloc[-1]-df_all['UTC'].iloc[0]).total_seconds()/3600
#night_hours = night_seconds / 3600.0
pct_night = 100 * night_hours / run_hours if run_hours else 0
#
night_cl=night_df[night_df['chisquared'] <= 0.009]
non_cloud_hours = gap_corrected_hours(night_cl, ts_col="UTC")
percent_le_0009 = 100 * non_cloud_hours/night_hours

summary_html = f"""
<h2>1. Annual Summary Statistics</h2>
<ul>
  <li><b>Site:</b> {site}</li>
  <li><b>Coordinates:</b> {latlonel}</li>
  <li><b>Time Range:</b> {start_str} to {end_str}</li>
  <li><b>Total Run Hours (18-6h):</b> {run_hours:.1f}</li>
  <li><b>Night Hours (sunalt<-18):</b> {night_hours:.1f}</li>
  <li><b>Run Hours percentage:</b> {pct_night:.1f}%</li>
  <li><b>Percentage w/o clouds:</b> {percent_le_0009:.1f}%</li>
</ul>
<h2>2. Night Sky Brightness (NSB) plots (interactive)</h2>
"""

# set plot sizes
plot_w=700
plot_h=400
df_use = _filtered_sqm(df_all, moon_thr=-10.0, chi_thr=0.009)
# Plot 1: SQM histogram — All (gray) vs Filtered (red)
if 'SQM' in df_all.columns:
    # All data
    SQM_all = pd.to_numeric(df_all['SQM'], errors='coerce').dropna()

    # Filtered subset (moonalt ≤ -10, χ² ≤ 0.009)
    df_f = _filtered_sqm(df_all, moon_thr=-10.0, chi_thr=0.009)
    SQM_filt = df_f['SQM'].astype(float) if len(df_f) else pd.Series([], dtype=float)

    # Consistent binning across both traces (0.1 mag bins)
    if len(SQM_all):
        xmin = np.floor(SQM_all.min()*10)/10
        xmax = np.ceil(SQM_all.max()*10)/10
    else:
        xmin, xmax = 18.0, 22.0
    xbins_cfg = dict(start=float(xmin), end=float(xmax), size=0.1)

    fig1 = go.Figure()
    fig1.add_trace(go.Histogram(
        x=SQM_all,
        name="All",
        opacity=0.55,
        marker=dict(color="#1f77b4"), # blue
        xbins=xbins_cfg,
        hovertemplate="SQM: %{x:.2f}<br>Count: %{y}<extra>All</extra>"
    ))
    fig1.add_trace(go.Histogram(
        x=SQM_filt,
        name="moonalt ≤ −10° & χ² ≤ 0.009",
        opacity=0.65,
        marker=dict(color="red"),
        xbins=xbins_cfg,
        hovertemplate="SQM: %{x:.2f}<br>Count: %{y}<extra>Filtered</extra>"
    ))

    fig1.update_layout(
        barmode="overlay",
        title="NSB Histogram",
        title_font=dict(size=24),
        title_x=0.5,
        xaxis_title="NSB (mag/arcsec²)",
        yaxis_title="Count",
        width=plot_w, height=plot_h,
        legend=dict(orientation="h", y=1.08, x=0.0)
    )

    pio.write_html(fig1, file=str(outdir / f"{label}_histogram.html"), auto_open=False)
    fig1.write_image(str(outdir / f"{label}_histogram.png"))
else:
    print("ℹ️ Histogram skipped: no SQM column.")

# Plot 2: Heatmap (15-min bins), wrapped to 17:00 → 07:00 MST, using ALL data
if 'UTC' in df_all.columns and 'SQM' in df_all.columns:
    # Parse UTC and convert to MST (America/Phoenix); fallback: UTC-7
    ts_utc = pd.to_datetime(df_all['UTC'], errors='coerce', utc=True)
    try:
        ts_mst = ts_utc.dt.tz_convert("America/Phoenix")
    except Exception:
        ts_mst = ts_utc - pd.Timedelta(hours=7)

    # Fractional local hour in [0,24)
    hour_frac = (
        ts_mst.dt.hour.astype(float)
        + ts_mst.dt.minute.astype(float)/60.0
        + ts_mst.dt.second.astype(float)/3600.0
    ) % 24.0

    bin_size = 0.25  # 15 min
    # Make bin_idx a Series aligned with df_all.index
    bin_idx = pd.Series(
        np.floor(hour_frac / bin_size).astype(int).clip(0, 95),
        index=df_all.index
    )

    # Night window: 17:00–23:45 (68..95) and 00:00–06:45 (0..27) → 56 bins
    start_idx    = int(17 / bin_size)   # 68
    end_idx_excl = int(7  / bin_size)   # 28 (exclusive)
    # sel_mask must be aligned Series
    sel_mask = (bin_idx >= start_idx) | (bin_idx < end_idx_excl)

    # Index df_all with aligned mask
    df_sel  = df_all.loc[sel_mask].copy()
    ts_sel  = ts_mst.loc[sel_mask]
    bins_sel = bin_idx.loc[sel_mask].to_numpy()

    # Wrap positions: 17:00..23:45 -> 0..27, 00:00..06:45 -> 28..55
    wrapped_pos = np.where(
        bins_sel >= start_idx,
        bins_sel - start_idx,
        (96 - start_idx) + bins_sel
    )

    # Prepare values
    df_sel['date'] = ts_sel.dt.date
    df_sel['bin_pos'] = wrapped_pos
    df_sel['SQM_num'] = pd.to_numeric(df_sel['SQM'], errors='coerce')

    heat = df_sel.pivot_table(index='bin_pos', columns='date',
                              values='SQM_num', aggfunc='mean')
    heat = heat.reindex(range(0, 56), axis=0)

    # Hour ticks every hour (4 bins), starting at 17:00
    tickvals = list(range(0, 56, 4))
    ticktext = [str(int((17 + 0.25*i) % 24)) for i in tickvals]

    # Optional gamma stretch for color contrast
    raw = heat.values.astype(float)
    zmin, zmax = np.nanmin(raw), np.nanmax(raw)
    den = (zmax - zmin) if np.isfinite(zmax - zmin) and (zmax - zmin) != 0 else 1.0
    z_norm = np.clip((raw - zmin) / den, 0, 1)
    gamma = 0.6
    z_gamma = z_norm ** gamma

    fig2 = go.Figure(data=go.Heatmap(
        z=z_gamma,
        customdata=raw.tolist(),  # show raw values on hover
        hovertemplate="NSB: %{customdata:.2f} mag/arcsec²<extra></extra>",
        x=[str(c) for c in heat.columns],
        y=np.arange(56),
        colorscale="Turbo",
        colorbar=dict(title=dict(text="NSB", side="right"), thickness=12),
        hoverongaps=False
    ))
    fig2.update_layout(
        title="NSB Heatmap — all data)",
        title_font=dict(size=24),
        title_x=0.5,
        xaxis=dict(title="Date"),
        yaxis=dict(title="Hour (MST)", tickmode="array",
                   tickvals=tickvals,
                   ticktext=ticktext),
        width=plot_w, height=plot_h
    )
    pio.write_html(fig2, file=str(outdir / f"{label}_heatmap.html"),
                   auto_open=False)
    fig2.write_image(str(outdir / f"{label}_heatmap.png"))
else:
    print("ℹ️ Heatmap skipped: missing UTC or SQM.")
#    
# Plot 3: Jellyfish (use filtered SQM only)
# --- Jellyfish: 2D histogram time-of-night vs SQM (filtered), stable 17→07 axis ---
df_use = _filtered_sqm(df_all, moon_thr=-10.0, chi_thr=0.009)
if len(df_use) and 'UTC' in df_use.columns:
    ts_utc = pd.to_datetime(df_use['UTC'], errors='coerce', utc=True)
    try:
        ts_mst = ts_utc.dt.tz_convert("America/Phoenix")
    except Exception:
        ts_mst = ts_utc - pd.Timedelta(hours=7)

    hour_frac = (
        ts_mst.dt.hour.astype(float)
        + ts_mst.dt.minute.astype(float) / 60.0
        + ts_mst.dt.second.astype(float) / 3600.0
    ) % 24.0
    sqm_vals = pd.to_numeric(df_use['SQM'], errors='coerce')

    m = hour_frac.notna() & sqm_vals.notna()
    hour = hour_frac.loc[m].to_numpy()
    yval = sqm_vals.loc[m].to_numpy()

    # Edges
    x_edges = np.arange(0.0, 24.0001, 0.25)  # 96 columns (15-min bins)
    y_min = float(np.nanmin(yval)) if yval.size else 20.0
    y_max = float(np.nanmax(yval)) if yval.size else 23.0
    y_edges = np.arange(np.floor(y_min*10)/10.0, np.ceil(y_max*10)/10.0 + 0.0001, 0.1)

    # 2D histogram over full 0–24, then wrap to 17→07
    H, _, _ = np.histogram2d(hour, yval, bins=[x_edges, y_edges])  # (96, Ny)
    start_idx = int(17 / 0.25)      # 68
    end_idx_excl = int(7 / 0.25)    # 28
    H_wrap = np.concatenate([H[start_idx:96, :], H[0:end_idx_excl, :]], axis=0)  # (56, Ny)

    # Axes for display
    # Use index 0..55 on x, and label ticks as 17..23,0..7
    x_idx = np.arange(56)
    tickvals = np.arange(0, 56, 4)
    ticktext = [str(int((17 + 0.25*i) % 24)) for i in tickvals]

    # y centers
    y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])  # (Ny,)

    # Color values (log for contrast), shape must be (Ny x 56)
    Z = np.log10(H_wrap.T + 1.0)  # transpose to Ny x 56

    fig3 = go.Figure(data=go.Heatmap(
        z=Z,
        x=x_idx,
        y=y_centers,
        colorscale="Turbo",
        colorbar=dict(title="log₁₀ count", thickness=12),
        hovertemplate=(
            "Hour: %{x} bins from 17:00<br>"
            "NSB: %{y:.2f} mag/arcsec²<br>"
            "log₁₀(count): %{z:.2f}<extra></extra>"
        ),
        hoverongaps=False
    ))

    fig3.update_layout(
        title="Jellyfish Plot, moonalt ≤ -10°, χ² ≤ 0.009",
        title_font=dict(size=24),
        title_x=0.5,
        xaxis=dict(
            title="MST",
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext
        ),
        yaxis=dict(title="NSB (mag/arcsec²)"),
        width=plot_w, height=plot_h
    )

    pio.write_html(fig3, file=str(outdir / f"{label}_jellyfish.html"), auto_open=False)
    fig3.write_image(str(outdir / f"{label}_jellyfish.png"))
else:
    print("ℹ️ Jellyfish skipped: no filtered rows or UTC missing.")
# Plot 4: Chi-squared Histogram (cap at 1.0; overflow -> last bin)
if 'chisquared' in df_all.columns:
    s = pd.to_numeric(df_all['chisquared'], errors='coerce')

    # Count overflow, then cap to 1.0 (put all >1 into last bin)
    overflow = (s > 1.0).sum()
    s_cap = s.clip(upper=1.0)

    # Optional: nudge exact 1.0 to ensure it lands inside the last bin if your
    # plotting lib treats the right edge as open; comment out if not needed.
    s_cap = np.where(s_cap >= 1.0, np.nextafter(1.0, 0.0), s_cap)

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
        showarrow=False, font=dict(size=12, color="#444"),
        bgcolor="rgba(255,255,255,0.6)"
    )

    # Label right edge as "≥1"
    tickvals = [0.0, 0.25, 0.5, 0.75, 1.0]
    ticktext = ["0.00", "0.25", "0.50", "0.75", "≥1"]

    fig4.update_layout(
        title="χ² Histogram (last bar contains all > 1.0)",
        title_x=0.5,
        bargap=0.02,
        xaxis=dict(title="χ²", range=[0, 1], tickmode="array",
                   tickvals=tickvals, ticktext=ticktext),
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
