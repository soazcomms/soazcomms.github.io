#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, os, shutil, sys, json, time, shlex, subprocess, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests
import io, csv

# ---------- tiny utils ----------
def run(cmd, cwd=None, check=True, capture=False):
    if isinstance(cmd, str): cmd = shlex.split(cmd)
    kw = dict(cwd=cwd, text=True)
    if capture: kw.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    p = subprocess.run(cmd, **kw)
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd, p.stdout if capture else None)
    return p

def git_identity(repo: Path):
    subprocess.call(["git","config","user.email","actions@github.com"], cwd=str(repo))
    subprocess.call(["git","config","user.name","github-actions"],     cwd=str(repo))

def git_hard_sync(repo: Path):
    subprocess.call(["git","reset","--hard"], cwd=str(repo))
    subprocess.call(["git","clean","-fd"],    cwd=str(repo))
    subprocess.call(["git","fetch","origin"], cwd=str(repo))
    subprocess.call(["git","checkout","main"],cwd=str(repo))
    subprocess.call(["git","reset","--hard","origin/main"], cwd=str(repo))

def git_commit_push(repo: Path, msg: str):
    subprocess.call(["git","add","-A"], cwd=str(repo))
    if subprocess.call(["git","diff","--cached","--quiet"], cwd=str(repo)) == 0:
        return
    subprocess.call(["git","commit","-m", msg], cwd=str(repo))
    if subprocess.call(["git","push","origin","main"], cwd=str(repo)) != 0:
        subprocess.call(["git","fetch","origin"], cwd=str(repo))
        subprocess.call(["git","reset","--hard","origin/main"], cwd=str(repo))
        subprocess.call(["git","add","-A"], cwd=str(repo))
        subprocess.call(["git","commit","-m","republish after reset"], cwd=str(repo))
        subprocess.call(["git","push","--force-with-lease","origin","main"], cwd=str(repo))

def site_from_label(label: str) -> str:
    return (label or "").split("_", 1)[0].strip()  # "DSN019-S_MtLemmon" -> "DSN019-S"

def measurement_from_label(label: str) -> str:
    # "DSN019-S_MtLemmon" → "DSN019S_MtLemmon"  (remove the dash)
    return (label or "").replace("-", "")

def ymd(d: str) -> str:
    # Accept YYYY-MM-DD (from Grafana) and return YYYYMMDD
    return d.split(" ")[0].replace("-", "")

def iso_range(start_day: str, stop_day: str) -> tuple[str, str]:
    # Convert YYYY-MM-DD or YYYY-MM-DD HH:MM:SS → ISO UTC Z range
    s = datetime.strptime(start_day.split(" ")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    e = datetime.strptime(stop_day.split(" ")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    return s.isoformat().replace("+00:00", "Z"), e.isoformat().replace("+00:00", "Z")

def looks_like_placeholder(url: str) -> bool:
    u = (url or "").strip().lower()
    return ("<your" in u) or ("{your" in u) or ("example" in u) or ("%3c" in u)  # catches encoded < >

def query_influx_csv(url, org, token, bucket, measurement, start_iso, stop_iso) -> str:
    flux = f'''
from(bucket: {json.dumps(bucket)})
  |> range(start: time(v: {json.dumps(start_iso)}), stop: time(v: {json.dumps(stop_iso)}))
  |> filter(fn: (r) => r["_measurement"] == {json.dumps(measurement)})
  |> filter(fn: (r) => contains(value: r["_field"], set: ["SQM","lum","chisquared","moonalt"]))
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time","SQM","lum","chisquared","moonalt"])
  |> rename(columns: {{"_time": "time"}})
  |> sort(columns: ["time"])
'''
    qurl = url.rstrip("/") + "/api/v2/query"
    r = requests.post(
        qurl,
        params={"org": org},
        data=flux.encode("utf-8"),
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "text/csv",
        },
        timeout=120
    )
    if r.status_code != 200:
        raise RuntimeError(f"Influx query {r.status_code}: {r.text[:400]}")
    # strip annotations and optional result/table cols
    lines = [ln for ln in r.text.splitlines() if not ln.startswith("#")]
    if not lines:
        return "time,SQM,lum,chisquared,moonalt\n"
    if lines[0].startswith("result,table,"):
        out = []
        for ln in lines:
            parts = ln.split(",")
            if len(parts) >= 3:
                out.append(",".join(parts[2:]))
        if out and not out[0].startswith("time,"):
            out.insert(0, "time,SQM,lum,chisquared,moonalt")
        return "\n".join(out) + ("\n" if out and not out[-1].endswith("\n") else "")
    if not lines[0].startswith("time,"):
        lines.insert(0, "time,SQM,lum,chisquared,moonalt")
    return "\n".join(lines) + ("\n" if lines and not lines[-1].endswith("\n") else "")

def fix_influx_csv(text: str, wanted=("SQM","lum","chisquared","moonalt")) -> str:
    """
    Normalize Influx CSV to: time,<wanted...>
    - removes annotation lines starting with '#'
    - drops 'result,table' columns if present
    - removes ',_result,0,' prefixes from data rows
    - guarantees a single header: time,<wanted present in data>
    """
    # strip comment/annotation lines and blanks
    raw_lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    if not raw_lines:
        return "time," + ",".join(wanted) + "\n"

    # csv-parse
    reader = csv.reader(raw_lines)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return "time," + ",".join(wanted) + "\n"

    # If header is the annotated one ('result,table,time,...'), drop the first two cols everywhere
    drop_two = False
    if rows and len(rows[0]) >= 3 and rows[0][0] == "result" and rows[0][1] == "table" and rows[0][2] == "time":
        drop_two = True

    # Some outputs have your desired header on line 1 and the annotated header on line 2.
    # Detect and prefer the clean header if present.
    prefer_clean_header = rows and rows[0] and rows[0][0] == "time"

    # Build cleaned table
    cleaned = []
    for r in rows:
        # remove leading annotated columns for data rows
        if drop_two and len(r) >= 3:
            r = r[2:]
        # also handle lines that start with an empty cell then '_result,0,...'
        if r and r[0] == "" and len(r) >= 3 and r[1] == "_result" and r[2] == "0":
            r = r[3:]
        # skip any residual duplicate annotated header
        if r and r[0] in ("result", "table", "_result"):
            continue
        cleaned.append(r)

    # If first row is the desired header, use it; otherwise assemble from present columns
    if prefer_clean_header:
        header = cleaned[0]
        data_rows = cleaned[1:]
    else:
        # figure out which of the wanted columns are present after cleaning
        header = cleaned[0] if cleaned and cleaned[0] and cleaned[0][0] == "time" else None
        if header is None:
            # try to find a header row containing 'time'
            for i, r in enumerate(cleaned[:3]):
                if r and "time" in r:
                    header = r
                    cleaned = cleaned[i+1:]
                    break
        if header is None:
            # fallback header
            header = ["time"] + list(wanted)
        data_rows = cleaned

    # Map indices and build final columns
    col_index = {name: i for i, name in enumerate(header)}
    final_cols = ["time"] + [c for c in wanted if c in col_index]
    # map original names to pretty header titles
    header_map = {
        "time": "time (UT)",
        "SQM": "rad (mag/sq asec)",
        "lum": "rad nW/cm2/sr",
        "chisquared": "chisquared",
        "moonalt": "Moon alt (deg)"
    }

    # build display header row
    pretty_cols = [header_map.get(c, c) for c in final_cols]

    # write out
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(pretty_cols)

    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}T")
    for r in data_rows:
        if not r:
            continue
        # skip any reappearing header rows
        if r[0] == "time":
            continue
        # Only keep rows whose first column looks like an ISO timestamp
        if not iso_re.match(r[0]):
            continue
        row = [r[col_index.get("time", 0)]]
        for c in final_cols[1:]:
            idx = col_index[c]
            row.append(r[idx] if idx < len(r) else "")
        w.writerow(row)

    return out.getvalue()
# ---------- main ----------
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, dest="label")
    ap.add_argument("--from",  required=True, dest="from_date")
    ap.add_argument("--to",    required=True, dest="to_date")
    ap.add_argument("--site-repo", default=str(Path("~/DSN/soazcomms.github.io").expanduser()), dest="site_repo")
    ap.add_argument("--out", dest="out")  # optional explicit output under site repo

    # NEW: allow explicit Influx creds via CLI (env fallback below)
    ap.add_argument("--influx-url", dest="influx_url",
                    default="https://us-east-1-1.aws.cloud2.influxdata.com")
    ap.add_argument("--influx-token", dest="influx_token")
    ap.add_argument("--influx-org", dest="influx_org", default="DSN")
    ap.add_argument("--influx-bucket", dest="influx_bucket", default="DSNdata")

    # legacy inputs (kept for compatibility; not used if Influx is set)
    ap.add_argument("--source")
    ap.add_argument("--cmd")
    return ap.parse_args()

def delete_non_csv(out_dir: Path):
    """Remove all files in out_dir that are not .csv files."""
    removed = 0
    for f in out_dir.iterdir():
        if f.is_file() and f.suffix.lower() != ".csv":
            try:
                f.unlink()
                removed += 1
            except Exception:
                debug_log(f"[clean] skip remove {f.name}")
                pass
    if removed: debug_log(f"[clean] removed {removed} non-CSV files")
def main():
    args = parse_args()

    repo = Path(args.site_repo).expanduser().resolve()
    if not repo.exists():
        print(f"ERROR: site repo not found: {repo}", file=sys.stderr)
        return 2

    git_identity(repo)
    git_hard_sync(repo)

    label8 = args.label[:8]
    ymd_from = ymd(args.from_date).replace("-","")
    ymd_to   = ymd(args.to_date).replace("-","")
    if args.out:
        # Respect the directory from --out, but normalize the filename
        out_dir = Path(args.out).expanduser().resolve().parent
        out_csv = out_dir / f"{args.label}_{ymd_from}_{ymd_to}.csv"
    else:
        out_dir = Path(args.site_repo).expanduser().resolve() / "analysis" / label[:8]
        out_csv = out_dir / f"{args.label}_{ymd_from}_{ymd_to}.csv"

    # Early exit if csv exists       
    if out_csv.exists() and out_csv.stat().st_size > 0:
        # usual status line so the HTML unblocks immediately
        delete_non_csv(out_dir)
        print(json.dumps({
            "status": f"✅ CSV already present for {args.label} {ymd_from}-{ymd_to}",
            "csv":     f"https://soazcomms.github.io/analysis/{label8}/{out_csv.name}",
            "csv_raw": f"https://raw.githubusercontent.com/soazcomms/soazcomms.github.io/main/analysis/{label8}/{out_csv.name}",
            "timestamp": int(time.time())
        }))
        sys.exit(0)
    
    try:
        out_csv.relative_to(repo)
    except ValueError:
        print(f"ERROR: --out must live under site repo: {repo}", file=sys.stderr)
        return 2
    # make sure:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # E out_dir before writing new CSV
    if os.path.exists(out_dir):
        for filename in os.listdir(out_dir):
            file_path = os.path.join(out_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Warning: failed to delete {file_path}: {e}")

    # Influx config: CLI > ENV
    INFLUX_URL    = (args.influx_url   or os.getenv("INFLUX_URL")   or "").strip()
    INFLUX_TOKEN  = (args.influx_token or os.getenv("INFLUX_TOKEN") or "").strip()
    INFLUX_ORG    = (args.influx_org   or os.getenv("INFLUX_ORG")   or "DSN").strip()
    INFLUX_BUCKET = (args.influx_bucket or os.getenv("INFLUX_BUCKET") or "DSNdata").strip()

    # Guard against placeholders / empty config
    if not INFLUX_URL or looks_like_placeholder(INFLUX_URL):
        print("ERROR: Influx URL not set. Use --influx-url https://<your-cloud2-host> or set INFLUX_URL", file=sys.stderr)
        return 2
    if not INFLUX_TOKEN or looks_like_placeholder(INFLUX_TOKEN):
        print("ERROR: Influx token not set. Use --influx-token *** or set INFLUX_TOKEN", file=sys.stderr)
        return 2

    # Fetch real CSV from Influx for Grafana window
#    site = site_from_label(args.label)
    meas = measurement_from_label(args.label)  # e.g., DSN019S_MtLemmon

    start_iso, stop_iso = iso_range(args.from_date, args.to_date)
    try:
        csv_text = query_influx_csv(INFLUX_URL, INFLUX_ORG, INFLUX_TOKEN, INFLUX_BUCKET,meas, start_iso, stop_iso)
        csv_text = fix_influx_csv(csv_text, wanted=("SQM","lum","chisquared","moonalt"))
        out_csv.write_text(csv_text)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    out_csv.write_text(csv_text)

    # commit & push
    rel = out_csv.relative_to(repo)
    git_commit_push(repo, f"Publish CSV for {args.label} {ymd_from}..{ymd_to}")

    csv_pages = f"https://soazcomms.github.io/{str(rel).replace(os.sep,'/')}"
    csv_raw   = f"https://raw.githubusercontent.com/soazcomms/soazcomms.github.io/main/{str(rel).replace(os.sep,'/')}"
    print(json.dumps({
        "status": f"✅ CSV ready for {args.label} {ymd_from}-{ymd_to}",
        "csv": csv_pages,
        "csv_raw": csv_raw,
        "timestamp": int(time.time())
    }))
    return 0

if __name__ == "__main__":
    sys.exit(main())
