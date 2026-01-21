#----
version="DSN_python V01"
version_date="01/21/2026"
print("DSN_generate_analysis.py version ",version_date)
#----
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
from astropy.time import Time
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_sun
import astropy.units as u

#******************
def altsun1(tlat,tlong,tele,utc):
    sun_time = Time(utc) #UTC time
    loc = EarthLocation.from_geodetic(tlong,tlat,tele)
    altaz = AltAz(obstime=sun_time, location=loc)
    alt_ang = get_sun(sun_time).transform_to(altaz).alt.degree
    return alt_ang
#******************
# calculate galactic latitude of zenith at times utc
# absolute galactic latitude |b| of the zenith
def z_MWlat(tlat, tlong, tele, utc):
    loc = EarthLocation.from_geodetic(
        lon=tlong*u.deg, lat=tlat*u.deg, height=tele*u.m)
    t = Time(utc, location=loc)
    # Zenith in the local AltAz frame
    zen_altaz = SkyCoord(
        alt=90*u.deg, az=0*u.deg, frame=AltAz(obstime=t, location=loc))
    # Convert to Galactic and return |b|
    b = zen_altaz.galactic.b.to_value(u.deg)
    return np.abs(b)
#******************
def ymd(d: str) -> str:
    # Accept YYYY-MM-DD (from Grafana) and return YYYYMMDD
    return d.split(" ")[0].replace("-", "")
#
parser = argparse.ArgumentParser()
parser.add_argument('--input_dir', required=True)
parser.add_argument('--from', dest='from_time', required=True)
parser.add_argument('--to', dest='to_time', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()

# Time-range label for plot axis titles
start_str = args.from_time
end_str = args.to_time
time_range_label = f"[{start_str[:10]} to {end_str[:10]}]"

in_dir = args.input_dir
label = args.label

start_time = pd.to_datetime(args.from_time, utc=True)
end_time = pd.to_datetime(args.to_time, utc=True)
start_str = start_time.strftime("%y-%m-%d %H:%M:%S")
end_str = end_time.strftime("%y-%m-%d %H:%M:%S")
ymd_from = ymd(args.from_time)
ymd_to   = ymd(args.to_time)
#
#outdir = Path("analysis") / label
outdir = Path(in_dir)
#outdir.mkdir(parents=True, exist_ok=True)
# Load site metadata
sites_df = pd.read_csv("DSNsites.csv", comment='#', header=None,
                       names=['lon', 'lat', 'el', 'sensor', 'ihead', 'dark',
                              'bright', 'label'])
sites_df['label'] = sites_df['label'].astype(str).str.strip()

# Lookup site info by label_strip
try:
    site_info = sites_df[sites_df['label'] == label].iloc[0]
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

num_files=len(all_files)
print(f"📄 Found {num_files} files: {all_files}")

df_list = []
for file in all_files:
    filepath = os.path.join(in_dir, file)
    try:
        df = pd.read_csv(filepath, comment='#', sep=None, engine='python')
        df['sourcefile'] = file
        df_list.append(df)
    except Exception as e:
        print(f"⚠️ Skipping {file}: {e}")

df_all = pd.concat(df_list, ignore_index=True)
df_all = df_all.rename(columns={
    "time (UT)": "UTC",
    "rad (mag/sq asec)": "SQM",
    "rad nW/cm2/sr": "lum",
    "chisquared": "chisquared",
    "Moon alt (deg)": "moonalt"
})

# Debug: print column order and sample data
print(f"Columns in df_all: {df_all.columns.tolist()}")
if len(df_all) > 0:
    print(f"Sample row:\n{df_all.iloc[0]}")

if 'UTC' in df_all.columns:
    df_all['UTC'] = pd.to_datetime(df_all['UTC'], utc=True, errors='coerce')
    df_all = df_all.dropna(subset=['UTC'])
    df_all = df_all[(df_all['UTC'] >= start_time) & (df_all['UTC'] <= end_time)]
    UTC=df_all['UTC']
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
def _filtered_sqm(df, moon_thr=-10.0, chi_thr=0.009, MW_thr=50.):
    """
    Return a copy of df filtered to good SQM rows that satisfy ALL:
      moonalt    <= moon_thr
      MWlat     > MW_thr
      chisquared <= chi_thr

    Ensures SQM is numeric and drops NaNs.
    Missing required columns => returns empty.
    """
    required = ("SQM", "moonalt", "MWlat", "chisquared")
    for c in required:
        if c not in df.columns:
            return df.iloc[0:0].copy()

    moonalt = pd.to_numeric(df["moonalt"], errors="coerce")
    mwlat  = pd.to_numeric(df["MWlat"], errors="coerce")
    chi     = pd.to_numeric(df["chisquared"], errors="coerce")
    m = (moonalt <= float(moon_thr)) & (mwlat > float(MW_thr)) & (chi <= float(chi_thr))

    out = df.loc[m].copy()
    out["SQM"] = pd.to_numeric(out["SQM"], errors="coerce")
    out = out.dropna(subset=["SQM"])
    return out
# plotting thresholds:
moon_thr=-10.
MW_thr=20.
chi_thr=0.009
#df_local = df_all.copy()
df_all['Local'] = df_all['UTC'].dt.tz_convert('America/Phoenix')
df_all['Date'] = df_all['Local'].dt.date
# Total (gap-aware)
run_hours = gap_corrected_hours(df_all, ts_col="UTC")
# Night only (sunalt <= -18)
df_all['sunalt']=altsun1(lat,lon,el,list(UTC))
df_all = df_all[df_all['sunalt'] <= -18]
UTC=df_all['UTC']
night_hours = gap_corrected_hours(df_all, ts_col="UTC")
#run_hours = (df_all['UTC'].iloc[-1]-df_all['UTC'].iloc[0]).total_seconds()/3600
#night_hours = night_seconds / 3600.0
pct_night = 100 * night_hours / run_hours if run_hours else 0
#
# FIX: Convert chisquared to numeric before comparison
night_cl = df_all[pd.to_numeric(df_all['chisquared'], errors='coerce') <= 0.009]
non_cloud_hours = gap_corrected_hours(night_cl, ts_col="UTC")
percent_le_0009 = 100 * non_cloud_hours/night_hours if night_hours > 0 else 0
# MW lats
df_all['MWlat']=z_MWlat(lat,lon,el,list(UTC))
summary_html = f"""
<h2>1. Summary Statistics</h2>
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
df_use = _filtered_sqm(df_all, moon_thr=-10.0, chi_thr=0.009, MW_thr=MW_thr)
# Plot 1: SQM histogram — All (gray) vs Filtered (red)
if 'SQM' in df_all.columns:
    # All data
    SQM_all = pd.to_numeric(df_all['SQM'], errors='coerce').dropna()

    # Filtered subset (moonalt ≤ -10, χ² ≤ 0.009)
    df_f = _filtered_sqm(df_all, moon_thr=-10.0, chi_thr=0.009, MW_thr=MW_thr)
    SQM_filt = df_f['SQM'].astype(float) if len(df_f) else pd.Series([], dtype=float)

    # SQM_filt is your filtered SQM Series/array
    sqm_vals = pd.to_numeric(SQM_filt, errors="coerce").dropna().to_numpy()

    if sqm_vals.size:
        # choose binning (match your histogram bins!)
        bin_size = 0.1  # <-- set to whatever you use (e.g., 0.1 or 0.25)
        lo = np.floor(sqm_vals.min() / bin_size) * bin_size
        hi = np.ceil(sqm_vals.max() / bin_size) * bin_size
        edges = np.arange(lo, hi + bin_size, bin_size)

        counts, edges = np.histogram(sqm_vals, bins=edges)
        peak_i = int(np.argmax(counts))
        sqm_peak = float((edges[peak_i] + edges[peak_i + 1]) / 2.0)  # bin center
    else:
        sqm_peak = None
    
    # Consistent binning across both traces (0.1 mag bins)
#    if len(SQM_all):
#        xmin = np.floor(SQM_all.min()*10)/10
#        xmax = np.ceil(SQM_all.max()*10)/10
#    else:
    xmin, xmax = 17.0, 23.0
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
        name=f"moonalt ≤ −10° & χ² ≤ 0.009 & Zenith-MW > {MW_thr:.0f}°",
        opacity=0.65,
        marker=dict(color="red"),
        xbins=xbins_cfg,
        hovertemplate="SQM: %{x:.2f}<br>Count: %{y}<extra>Filtered</extra>"
    ))
    fig1.add_vline(
        x=sqm_peak,
        line_width=2,
        line_dash="dash",
        line_color="gray"
    )  
    fig1.add_annotation(
        x=sqm_peak + 0.02,
        y=0.5,
        yref="paper",
        text=f"Mode = {sqm_peak:.2f}",
        showarrow=False,
        xanchor="left",
        yanchor="top",
        font=dict(size=12),
        bgcolor="rgba(255,255,255,0.7)"
    )
    fig1.update_layout(
        barmode="overlay",
        title="NSB Histogram",
        title_font=dict(size=24),
        title_x=0.5,
        xaxis_title=f"NSB (mag/arcsec²) {time_range_label}",
        yaxis_title="Count",
        width=int(plot_w*1.5), height=int(plot_h*1.5),
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
        title="NSB Heatmap — all data",
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
df_use = _filtered_sqm(df_all, moon_thr=-10.0, chi_thr=0.009, MW_thr=MW_thr)
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
#    y_min = float(np.nanmin(yval)) if yval.size else 20.0
#    y_max = float(np.nanmax(yval)) if yval.size else 23.0
    y_min = 18.
    y_max = 23.
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
        title=f"Jellyfish Plot -- moonalt ≤ -10°, χ² ≤ 0.009 & Zenith-MW > {MW_thr:.0f}°",
        title_font=dict(size=16),
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
#
# Plot 4: Chi-squared Histogram (explicit overflow bin ≥1)
# Plot 4: Chi-squared Histogram with overflow bin ≥1
if 'chisquared' in df_all.columns:
    s = pd.to_numeric(df_all['chisquared'], errors='coerce').dropna()

    # Define bins below 1.0
    bin_edges = np.linspace(0, 1, 100, endpoint=False)  # up to <1.0
    hist, edges = np.histogram(s[s < 1.0], bins=bin_edges)

    # Overflow bin count (all >= 1.0)
    overflow = int((s >= 1.0).sum())

    # Centers: normal bins + one overflow bin
    bin_centers = (edges[:-1] + edges[1:]) / 2
    bin_centers = np.append(bin_centers, 1.0)  # place overflow bar at x=1.0

    hist = np.append(hist, overflow)

    # Labels: normal ticks plus "≥1"
    tickvals = list(np.linspace(0, 1, 5)) + [1.0]
    ticktext = [f"{v:.2f}" for v in np.linspace(0, 1, 5)] + ["≥1"]

    # Build bar plot
    fig4 = go.Figure(go.Bar(
        x=bin_centers,
        y=hist,
        width=[edges[1]-edges[0]] * (len(hist)-1) + [edges[1]-edges[0]*2],
        marker=dict(color="steelblue"),
        hovertemplate="χ² bin: %{x:.3f}<br>Count: %{y}<extra></extra>"
    ))

    # Red vertical line at 0.009
    fig4.add_vline(
        x=0.009, line_width=2, line_dash="dash", line_color="red",
        annotation_text="0.009", annotation_position="top right"
    )

    fig4.update_layout(
        title="χ² Histogram (last bar = all ≥ 1.0)",
        title_x=0.5,
        bargap=0.02,
        xaxis=dict(title="χ²", tickmode="array", tickvals=tickvals, ticktext=ticktext),
        yaxis=dict(title="Count"),
        width=plot_w, height=plot_h
    )

    # Save
    pio.write_html(fig4, file=str(outdir / f"{label}_chisq.html"), auto_open=False)
    fig4.write_image(str(outdir / f"{label}_chisq.png"))

# ============================================================
# LST-folded SQM (χ² < 0.09 & moonalt < -10°)
# Points folded into one "night" vs Local Sidereal Time (0-24h),
# with a faint-envelope band (faintest and 0.05 mag brighter),
# plus binned medians with(out) error bars = stdev in each LST bin.
# ============================================================
try:
    if not {'SQM', 'chisquared', 'moonalt', 'UTC'}.issubset(df_all.columns):
        raise ValueError("Missing one or more required columns for LST plot (SQM, chisquared, moonalt, UTC).")

    # Filter: χ² < 0.09 AND moonalt < -10
    sq = pd.to_numeric(df_all['SQM'], errors='coerce')
    chi = pd.to_numeric(df_all['chisquared'], errors='coerce')
    ma  = pd.to_numeric(df_all['moonalt'], errors='coerce')

    m_lst = (chi < 0.09) & (ma < -10.0) & np.isfinite(sq) & (sq <= 23.0)
    df_lst = df_all.loc[m_lst, ['UTC', 'SQM']].copy()
    df_lst['SQM'] = pd.to_numeric(df_lst['SQM'], errors='coerce')
    df_lst = df_lst.dropna(subset=['UTC', 'SQM'])

    if len(df_lst) < 10:
        print("⚠️ Not enough filtered points for LST plot; skipping.")
    else:
        # Compute Local Sidereal Time (hours, 0-24) using site location
        loc = EarthLocation.from_geodetic(lon=lon*u.deg, lat=lat*u.deg, height=el*u.m)
        t = Time(np.array(df_lst['UTC'].dt.to_pydatetime()), location=loc)
        lst_hours = t.sidereal_time('apparent').hour
        df_lst['LST'] = np.mod(np.array(lst_hours, dtype=float), 24.0)

        # Bin in LST to compute median, stdev, and faint envelope
        bin_hours = 10.0/60.0  # 10-minute bins
        df_lst['bin'] = (np.floor(df_lst['LST'] / bin_hours) * bin_hours) + (bin_hours/2.0)

        g = df_lst.groupby('bin')['SQM']
        b_centers = g.median().index.to_numpy(dtype=float)
        med = g.median().to_numpy(dtype=float)
        std = g.std(ddof=0).to_numpy(dtype=float)  # population stdev
        # Median-based bands/envelopes in *brightness* space:
        # 10% band: ±10% brightness around median; 20% envelope: ±20% brightness.
        dm10 = 2.5 * np.log10(1.10)
        dm20 = 2.5 * np.log10(1.20)
        faint_band = med + dm10
        bright_band = med - dm10
        faint_env  = med + dm20
        bright_env = med - dm20

        # Sort by bin center for plotting
        order = np.argsort(b_centers)
        x = b_centers[order]
        med = med[order]
        std = std[order]
        faint_band = faint_band[order]
        bright_band = bright_band[order]
        faint_env = faint_env[order]
        bright_env = bright_env[order]

        fig5 = go.Figure()

        # Raw folded points (light blue)
        fig5.add_trace(go.Scattergl(
            x=df_lst['LST'],
            y=df_lst['SQM'],
            mode='markers',
            name='χ² < 0.09 & moonalt < -10° (points)',
            marker=dict(size=0.5, color='green', opacity=1),
            hovertemplate="LST %{x:.2f} h<br>SQM %{y:.3f}<extra></extra>",
        ))

        # Faint edge (orange) - smooth spline
        fig5.add_trace(go.Scatter(
            x=x, y=faint_band,
            mode='lines',
            name='Faint band (+10% brightness equiv)',
            line=dict(color='orange', width=2, shape='spline'),
            hovertemplate="LST %{x:.2f} h<br>Faint %{y:.3f}<extra></extra>",
        ))

        
        # Envelope edges (±20% brightness equiv) - dashed
        fig5.add_trace(go.Scatter(
            x=x, y=faint_env,
            mode='lines',
            name='Envelope faint (+20% bright equiv)',
            line=dict(color='orange', width=1.5, dash='dash', shape='spline'),
            hovertemplate="LST %{x:.2f} h<br>Env faint %{y:.3f}<extra></extra>",
        ))
        fig5.add_trace(go.Scatter(
            x=x, y=bright_env,
            mode='lines',
            name='Envelope bright (-20% bright equiv)',
            line=dict(color='lightcoral', width=1.5, dash='dash', shape='spline'),
            hovertemplate="LST %{x:.2f} h<br>Env bright %{y:.3f}<extra></extra>",
        ))

# Brighter edge (light red) + fill to faint edge to make a band
        fig5.add_trace(go.Scatter(
            x=x, y=bright_band,
            mode='lines',
            name='Bright band (-10% brightness equiv)',
            line=dict(color='lightcoral', width=2, shape='spline'),
            fill='tonexty',
            fillcolor='rgba(255, 160, 160, 0.22)',
            hovertemplate="LST %{x:.2f} h<br>Bright %{y:.3f}<extra></extra>",
        ))

        # Median with(out) error bars (std in bin)
        fig5.add_trace(go.Scatter(
            x=x, y=med,
            mode='markers+lines',
            name='Median ± stdev (per bin)',
            line=dict(color='#0000FF', width=1.25, shape='spline'),
            marker=dict(size=9.375, color='#0000FF', opacity=0.2),
            # error bars: line only (no caps)
#            error_y=dict(type='data', array=std, visible=True, thickness=1.25, width=0, color='#0000FF'),
            hovertemplate="LST %{x:.2f} h<br>Median %{y:.3f}<br>σ %{customdata:.3f}<extra></extra>",
            customdata=std
        ))

        
        # Y-axis limits: ±0.5 mag beyond brightest/faintest values in this plot
        try:
            vals_for_ylim = []
            try:
                vals_for_ylim.append(np.asarray(med, dtype=float))
            except Exception:
                pass
            try:
                vals_for_ylim.append(np.asarray(faint_band, dtype=float))
            except Exception:
                pass
            try:
                vals_for_ylim.append(np.asarray(bright_band, dtype=float))
            except Exception:
                pass
            vv = np.concatenate([v[np.isfinite(v)] for v in vals_for_ylim if v is not None and len(v) > 0]) if vals_for_ylim else np.array([])
            if vv.size:
                brightest = float(np.nanmin(vv))
                faintest  = float(np.nanmax(vv))
                y_range = [faintest + 0.5, brightest - 0.5]  # reversed mag axis
            else:
                y_range = None
        except Exception:
            y_range = None

        fig5.update_layout(
            title="SQM folded by Local Sidereal Time (χ² < 0.09 & moonalt < -10°)",
            title_x=0.5,
            xaxis=dict(title=f"Local Sidereal Time (hours) {time_range_label}", range=[0, 24]),
            legend=dict(orientation="h", x=0.5, xanchor="center", y=1.02, yanchor="bottom", font=dict(size=9)),
            yaxis=dict(title="SQM (mag/arcsec²)", autorange='reversed'),
            width=int(plot_w*1.5), height=int(plot_h*1.5),
        )

        if y_range is not None:
            fig5.update_yaxes(range=y_range)

        # Save
        pio.write_html(fig5, file=str(outdir / f"{label}_lst.html"), auto_open=False)
        fig5.write_image(str(outdir / f"{label}_lst.png"))
except Exception as e:
    print(f"⚠️ LST-folded plot failed: {e}")

# -------------------------------
# LST-folded SQM "one-night" plot
# Filters: chisquared < 0.09 AND moonalt < -10 AND SQM <= 23
# X: Local Sidereal Time (0..24 h)
# Y: SQM (mag/arcsec^2), inverted (fainter up)
# Shows:
#  - all filtered points (light blue)
#  - binned median with error bars = stdev per bin (no caps)
#  - a faint-side band between +10% and +20% (brightness) relative to median
#    (i.e., +Δmag10 .. +Δmag20), smoothed with a periodic Fourier fit
# -------------------------------
try:
    # Require columns
    for c in ("SQM", "chisquared", "moonalt", "UTC"):
        if c not in df_all.columns:
            raise ValueError("Missing one or more required columns for LST plot (SQM, chisquared, moonalt, UTC).")

    # Filter rows
    df_lst = df_all.copy()
    df_lst["SQM"] = pd.to_numeric(df_lst["SQM"], errors="coerce")
    df_lst["chisquared"] = pd.to_numeric(df_lst["chisquared"], errors="coerce")
    df_lst["moonalt"] = pd.to_numeric(df_lst["moonalt"], errors="coerce")

    df_lst = df_lst[
        (df_lst["chisquared"] < 0.09) &
        (df_lst["moonalt"] < -10.0) &
        (df_lst["SQM"].notna()) &
        (df_lst["SQM"] <= 23.0) &
        (df_lst["UTC"].notna())
    ].copy()

    if len(df_lst) < 50:
        print("⚠️ Not enough filtered points for LST plot; skipping.")
    else:
        # Compute LST (hours) for each timestamp
        loc = EarthLocation.from_geodetic(lon=lon*u.deg, lat=lat*u.deg, height=el*u.m)
        t = Time(list(df_lst["UTC"]), location=loc)
        lst_hours = t.sidereal_time("apparent").hour
        df_lst["LST"] = np.mod(np.array(lst_hours, dtype=float), 24.0)

        # Bin in LST (10-minute bins)
        bin_hours = 10.0/60.0
        df_lst["bin"] = (np.floor(df_lst["LST"] / bin_hours) * bin_hours) + (bin_hours/2.0)

        g = df_lst.groupby("bin")["SQM"]
        binned = pd.DataFrame({
            "LST": g.median().index.values.astype(float),
            "median": g.median().values.astype(float),
            "stdev": g.std(ddof=0).values.astype(float),
            "n": g.size().values.astype(int),
        })

        # Keep only bins with at least a few points (stable stdev)
        binned = binned[binned["n"] >= 5].sort_values("LST").reset_index(drop=True)

        if len(binned) < 10:
            print("⚠️ Not enough populated bins for LST plot; skipping.")
        else:
            # Convert brightness fractions to mag deltas (faint side = +Δmag)
            dmag10 = 2.5*np.log10(1.10)  # ~0.1035 mag
            dmag20 = 2.5*np.log10(1.20)  # ~0.1980 mag
            band_inner = binned["median"] + dmag10
            band_outer = binned["median"] + dmag20

            # Periodic Fourier fit for smooth curves
            def fourier_fit_periodic(x, y, period=24.0, K=6):
                x = np.asarray(x, dtype=float)
                y = np.asarray(y, dtype=float)
                ok = np.isfinite(x) & np.isfinite(y)
                x = x[ok]
                y = y[ok]
                if x.size < (2*K + 1):
                    return None

                w = 2*np.pi/period
                cols = [np.ones_like(x)]
                for k in range(1, K+1):
                    cols.append(np.cos(k*w*x))
                    cols.append(np.sin(k*w*x))
                A = np.column_stack(cols)
                # Ridge-regularized least squares (more stable than lstsq for near-singular A)
                lam = 1e-6
                with np.errstate(divide="ignore", invalid="ignore",
                                 over="ignore", under="ignore"):
                    try:
                        AtA = A.T @ A
                        AtY = A.T @ y
                        AtA = AtA + lam * np.eye(AtA.shape[0])
                        coef = np.linalg.solve(AtA, AtY)
                    except Exception:
                        coef, *_ = np.linalg.lstsq(A, y, rcond=None)

                def eval_fn(xq):
                    xq = np.asarray(xq, dtype=float)
                    colsq = [np.ones_like(xq)]
                    for k in range(1, K+1):
                        colsq.append(np.cos(k*w*xq))
                        colsq.append(np.sin(k*w*xq))
                    Aq = np.column_stack(colsq)
                    with np.errstate(divide="ignore", invalid="ignore",
                                     over="ignore", under="ignore"):
                        yq = Aq @ coef
                    yq = np.asarray(yq, float)
                    yq[~np.isfinite(yq)] = np.nan
                    return yq

                return eval_fn

            x_bins = binned["LST"].to_numpy()
            f_med = fourier_fit_periodic(x_bins, binned["median"].to_numpy(), K=6)
            if f_med is None:
                # Fallback: use raw (still plotted)
                x_smooth = x_bins
                med_smooth = binned["median"].to_numpy()
            else:
                x_smooth = np.linspace(0.0, 24.0, 481)  # ~3-min resolution
                med_smooth = f_med(x_smooth)

            inner_smooth = med_smooth + dmag10
            outer_smooth = med_smooth + dmag20

            # Figure (50% larger)
            lst_w = int(plot_w * 1.5)
            lst_h = int(plot_h * 1.5)

            fig_lst = go.Figure()

            # Raw points (light blue, small)
            fig_lst.add_trace(go.Scattergl(
                x=df_lst["LST"],
                y=df_lst["SQM"],
                mode="markers",
                name="SQM",
                marker=dict(size=2, color="green", opacity=0.8),
                hovertemplate="LST %{x:.2f} h<br>SQM %{y:.3f}<extra></extra>",
            ))

            # Faint-side band between +10% and +20% (brightness) of median
            # Plot outer first, then fill to inner
            fig_lst.add_trace(go.Scatter(
                x=x_smooth,
                y=outer_smooth,
                mode="lines",
                name="Faint envelope (+20%)",
                line=dict(color="lightcoral", width=2),
                hovertemplate="LST %{x:.2f} h<br>Env20 %{y:.3f}<extra></extra>",
            ))
            fig_lst.add_trace(go.Scatter(
                x=x_smooth,
                y=inner_smooth,
                mode="lines",
                name="Faint band (+10%)",
                line=dict(color="orange", width=2),
                fill="tonexty",
                fillcolor="rgba(255,160,122,0.25)",  # light red-ish
                hovertemplate="LST %{x:.2f} h<br>Band10 %{y:.3f}<extra></extra>",
            ))

            # Median with(out) error bars (no caps), smaller but brighter marker
            fig_lst.add_trace(go.Scatter(
                x=binned["LST"],
                y=binned["median"],
                mode="markers+lines",
                name="Binned median", # ±σ",
                line=dict(width=2, color="#0000FF"),
                marker=dict(size=1.5, color="#0000FF", opacity=1.0, line=dict(color="white", width=0.5)),
 #               error_y=dict(
 #                   type="data",
 #                   array=binned["stdev"].fillna(0).to_numpy(),
 #                   visible=True,
 #                   thickness=1,
 #                   width=0,  # no caps
 #               ),
                customdata=binned["stdev"].fillna(0).to_numpy(),
                hovertemplate="LST %{x:.2f} h<br>Median %{y:.3f}<br>σ %{customdata:.3f}<extra></extra>",
            ))


            # Tight y-range: ±0.5 mag beyond brightest/faintest of median+band (ignore raw scatter outliers)
            try:
                y_parts = [binned['median'].to_numpy(dtype=float)]
                if inner_smooth is not None:
                    y_parts.append(np.asarray(inner_smooth, dtype=float))
                if outer_smooth is not None:
                    y_parts.append(np.asarray(outer_smooth, dtype=float))
                y_all = np.concatenate([p[np.isfinite(p)] for p in y_parts if p is not None and np.size(p) > 0])
                if y_all.size >= 2:
                    y_lo = float(np.nanmin(y_all))  # brightest (smaller mag)
                    y_hi = float(np.nanmax(y_all))  # faintest (larger mag)
                    y_range = [y_hi + 0.5, y_lo - 0.5]  # keep mag axis inverted
                else:
                    y_range = None
            except Exception:
                y_range = None
            except Exception:
                y_range = None

            fig_lst.update_layout(
                title="LST-folded SQM (χ²<0.09 & moonalt<-10°)",
                title_x=0.5,
            xaxis=dict(title=f"Local Sidereal Time (hours) {time_range_label}", range=[0, 24]),
                yaxis=dict(title="SQM (mag/arcsec²)", autorange=False, range=y_range),
                width=lst_w, height=lst_h,
                legend=dict(orientation="h", x=0.5, xanchor="center", y=1.02, yanchor="bottom", font=dict(size=9)),
            )


            # Bottom-left stats (minima of binned curves)
            try:
                min_med = float(np.nanmax(binned["median"].to_numpy(dtype=float)))
                min_band10 = float(np.nanmax(np.asarray(band_inner, dtype=float)))
                min_env20 = float(np.nanmax(np.asarray(band_outer, dtype=float)))
                stats_txt = (
                    f"Faintest binned median: {min_med:.2f}<br>"
                    f"Faintest 10% band edge: {min_band10:.2f}<br>"
                    f"Faintest 20% envelope edge: {min_env20:.2f}"
                )
                fig_lst.add_annotation(
                    xref="paper", yref="paper", x=0.01, y=0.01,
                    text=stats_txt, showarrow=False,
                    align="left",
                    font=dict(size=10),
                    bgcolor="rgba(255,255,255,0.6)",
                    bordercolor="rgba(0,0,0,0.25)",
                    borderwidth=1,
                )
            except Exception:
                pass

            # Save
            pio.write_html(fig_lst, file=str(outdir / f"{label}_lst.html"), auto_open=False)
            fig_lst.write_image(str(outdir / f"{label}_lst.png"))
            print("✅ Wrote LST-folded plot.")
except Exception as e:
    print(f"⚠️ LST-folded plot failed: {e}")

# Generate main dashboard HTML
main_html = f"<html><head><title>{label} Analysis</title></head><body>\n"
main_html += f"<h1>{label} Analysis</h1>\n"
timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
main_html += f"<p style='font-size:small'>Generated: {timestamp}</p>\n"
main_html += summary_html +"\n"  # 👈 Include site summary

for plot_type in ["histogram", "heatmap", "jellyfish", "chisq", "lst"]:
    html_file = str(outdir / f"{label}_{plot_type}.html")
    if os.path.exists(html_file):
        with open(html_file) as f:
            main_html += f.read() + "\n"
    else:
        main_html += f"<p>⚠️ Missing {plot_type} plot for {html_file}.</p>\n"

main_html += "</body></html>"

# Generate main HTML wrapper
output_path = outdir / f"{label}.analysis.html"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(main_html)
    f.close()
print(f"✅ Wrote main HTML to {output_path}")

outdir = Path(outdir).resolve()    
existing = sorted(outdir.glob(f"{label}_*.html"))
num_files=len(existing)
print(f"🧾 Found {num_files} individual plot HTML files.")
#
output_path=outdir / f"files_{ymd_from}_{ymd_to}"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(str(num_files)+" files\n")
    f.close()
