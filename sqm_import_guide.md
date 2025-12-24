# Dark Sky Network SQM Data Import Guide
## Complete Setup for 10 Years of Data (Avoiding Partition Issues!)

## 🎯 Your Data Structure

**File Format:** `.dat` files with semicolon separators
**Device:** Sky Quality Meter (SQM-LE)
**Instrument:** DSN024-S at Winer Observatory, Arizona
**Data Points:** ~200 readings per day × 365 days × 10 years = **730,000 points**

**Columns (6 fields):**
1. UTC Timestamp (2025-12-15T00:13:00.082)
2. Local Timestamp 
3. Temperature (°C)
4. Voltage/Flag
5. Frequency (counter value)
6. MSAS (magnitudes per square arcsecond - sky brightness)

---

## ✅ Optimal InfluxDB Schema (Partition Problem SOLVED!)

### Schema Design:
```
measurement: "sky_brightness"

tags:
  - instrument_id: "DSN024-S"
  - location: "USA-Arizona-Elgin-DSN024"
  - device_type: "SQM-LE"
  - data_supplier: "Winer Observatory"

fields:
  - msas: 19.94 (mag/arcsec²)
  - temperature_c: 28.29
  - frequency: 5212 (integer)
  - voltage: 1269670.80
  - latitude: 31.6656
  - longitude: -110.6018
  - elevation: 1516.0
  - serial_number: "7821"

timestamp: utc_timestamp
```

### Why This Avoids Partition Problems:

✓ **Single measurement** instead of 200 separate ones
✓ **Low tag cardinality**: 4 tags with ~200 unique combinations max
✓ **Yearly partitions**: 10 shards instead of 3,650 daily shards
✓ **Series cardinality**: ~200 (excellent!)

❌ **What NOT to do:**
- Don't create separate measurement per instrument (DSN024-S, DSN025-S, etc.)
- Don't use timestamp components as tags (day, hour, etc.)
- Don't use MSAS value ranges as tags

---

## 📦 Step-by-Step Import Process

### Step 1: Install Dependencies
```bash
pip install influxdb-client
```

### Step 2: Set Up InfluxDB Cloud Serverless (Recommended)

1. **Sign up:** https://cloud2.influxdata.com/signup
2. **Create bucket:**
   - Name: `dark_sky_monitoring`
   - Retention: **Infinite** (for 10 years of data)
   - **CRITICAL:** Don't set short retention!
3. **Generate token:**
   - Go to: Settings → API Tokens → Generate API Token
   - Permissions: Read/Write to `dark_sky_monitoring` bucket
   - Copy token (you won't see it again!)

### Step 3: Configure Import Script

Edit `import_sqm_to_influxdb.py`:

```python
# For InfluxDB Cloud Serverless
INFLUXDB_URL = "https://us-east-1-1.aws.cloud2.influxdata.com"  # Your region
INFLUXDB_TOKEN = "your-actual-token-here"
INFLUXDB_ORG = "your-email@example.com"  # Usually your email
INFLUXDB_BUCKET = "dark_sky_monitoring"
```

### Step 4: Test with Single File (DRY RUN)

```bash
# Test parse without writing
python import_sqm_to_influxdb.py DSN024-S_2025-050.dat --dry-run
```

Expected output:
```
Processing: DSN024-S_2025-050.dat
Instrument: DSN024-S
Location: USA-Arizona-Elgin-DSN024
...
✓ Import complete!
  Total points: 1,193
```

### Step 5: Import Single File (REAL)

```bash
# Actually write to InfluxDB
python import_sqm_to_influxdb.py DSN024-S_2025-050.dat
```

### Step 6: Verify Data in InfluxDB

**Option A: Web UI**
1. Go to InfluxDB Cloud → Data Explorer
2. Select bucket: `dark_sky_monitoring`
3. Select measurement: `sky_brightness`
4. Select field: `msas`
5. Click "Submit" → Should see your data!

**Option B: CLI Query**
```bash
influx query '
  from(bucket: "dark_sky_monitoring")
    |> range(start: -7d)
    |> filter(fn: (r) => r._measurement == "sky_brightness")
    |> filter(fn: (r) => r._field == "msas")
    |> limit(n: 10)
'
```

### Step 7: Import All 10 Years of Data

**Option A: All files at once**
```bash
# If all .dat files in one directory
python import_sqm_to_influxdb.py /path/to/data/*.dat
```

**Option B: Year by year (recommended for testing)**
```bash
python import_sqm_to_influxdb.py data_2015/*.dat
python import_sqm_to_influxdb.py data_2016/*.dat
...
python import_sqm_to_influxdb.py data_2024/*.dat
```

**Option C: Parallel import (fastest)**
```bash
# Import multiple years simultaneously
python import_sqm_to_influxdb.py data_2015/*.dat &
python import_sqm_to_influxdb.py data_2016/*.dat &
python import_sqm_to_influxdb.py data_2017/*.dat &
wait
```

---

## ⏱️ Expected Import Time

For 730,000 points:
- **Batch size:** 5,000 points
- **Batches:** 146 batches
- **Time per batch:** ~2-5 seconds
- **Total time:** 10-15 minutes (single file)
- **Parallel import:** 5-10 minutes (if multiple cores)

---

## 💰 Cost Estimate (InfluxDB Cloud Serverless)

For 730,000 points one-time import:

**Data In:** 730k points × ~100 bytes = ~73 MB = $0.12
**Storage:** 73 MB × 720 hours (month) = 52 GB-hours = $0.26/month
**Queries:** Development/testing queries = ~$0.50
**Total first month:** ~$1.00

**Ongoing monthly cost:** $0.26 for storage (no new writes)

**Tip:** Use annual plan for discount if storing long-term!

---

## 🔍 Post-Import Validation

### Check 1: Total Point Count
```sql
SELECT COUNT(*) 
FROM sky_brightness
```
Expected: ~730,000

### Check 2: Time Range Coverage
```sql
SELECT 
  MIN(time) as first_reading,
  MAX(time) as last_reading
FROM sky_brightness
```
Expected: 10-year span from 2015 to 2025

### Check 3: Instruments Imported
```sql
SELECT DISTINCT instrument_id 
FROM sky_brightness
```
Expected: DSN024-S (and any other instruments)

### Check 4: Data Quality - MSAS Range
```sql
SELECT 
  MIN(msas) as darkest_sky,
  MAX(msas) as brightest_sky,
  AVG(msas) as average_sky
FROM sky_brightness
WHERE instrument_id = 'DSN024-S'
```
Expected: 
- Darkest: ~21.5-22 mag/arcsec² (pristine dark sky)
- Brightest: ~15-17 mag/arcsec² (twilight/moonlight)
- Average: ~19-20 mag/arcsec²

---

## 📊 Example Queries for Dark Sky Analysis

### Sky Quality Over Time
```sql
SELECT 
  DATE_BIN('1 day', time) as day,
  AVG(msas) as avg_brightness
FROM sky_brightness
WHERE instrument_id = 'DSN024-S'
  AND time > now() - interval '1 year'
GROUP BY day
ORDER BY day
```

### Nightly Sky Quality (Best Hour)
```sql
SELECT 
  DATE(time) as night,
  MAX(msas) as darkest_reading,
  AVG(msas) as avg_brightness
FROM sky_brightness
WHERE time > now() - interval '30 days'
GROUP BY night
ORDER BY night DESC
```

### Temperature vs Sky Brightness Correlation
```sql
SELECT 
  temperature_c,
  AVG(msas) as avg_sky_brightness
FROM sky_brightness
WHERE time > now() - interval '1 year'
GROUP BY temperature_c
ORDER BY temperature_c
```

### Monthly Statistics
```sql
SELECT 
  DATE_TRUNC('month', time) as month,
  AVG(msas) as avg_brightness,
  MIN(msas) as brightest,
  MAX(msas) as darkest,
  COUNT(*) as reading_count
FROM sky_brightness
WHERE instrument_id = 'DSN024-S'
GROUP BY month
ORDER BY month DESC
```

---

## 🛠️ Troubleshooting

### Error: "Token is invalid"
→ Regenerate token in InfluxDB Cloud UI
→ Make sure token has Read/Write permissions

### Error: "Bucket not found"
→ Create bucket in InfluxDB UI first
→ Double-check bucket name spelling

### Error: "Series cardinality too high"
→ This shouldn't happen with our schema!
→ Check that instrument_id is in tags, not fields

### Slow import (>1 hour for 730k points)
→ Increase BATCH_SIZE to 10000
→ Check network speed
→ Use parallel import

### Missing data points after import
→ Check for parse errors in output
→ Verify timestamp format matches
→ Look for files with different column orders

---

## 🎓 Next Steps After Import

1. **Set up Grafana dashboard** for visualization
2. **Create downsampling** for old data (>2 years)
3. **Set up alerts** for unusual sky brightness
4. **Calculate light pollution trends** over 10 years
5. **Compare multiple instruments** if you have more

---

## 📚 Additional Resources

- InfluxDB Flux queries: https://docs.influxdata.com/flux/
- Dark Sky Network: https://www.darksky.org/
- SQM data format: http://www.darksky.org/measurements
- Grafana dashboards: https://grafana.com/

---

## ✅ Final Checklist

- [ ] InfluxDB Cloud account created
- [ ] Bucket created with infinite retention
- [ ] API token generated
- [ ] Python dependencies installed
- [ ] Import script configured
- [ ] Test import completed (1 file)
- [ ] Data verified in UI
- [ ] Full import running
- [ ] Post-import validation passed
- [ ] Queries working as expected

**You're avoiding the partition problem because:**
- ✓ Single measurement (not 200)
- ✓ Low tag cardinality (~200 series)
- ✓ Proper field usage for high-cardinality data
- ✓ Appropriate data model for time series

**Congratulations! Your 10 years of dark sky data will import cleanly!** 🌌
