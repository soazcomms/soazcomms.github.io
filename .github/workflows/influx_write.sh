#!/bin/bash

# Usage: ./influx_write.sh <input_file> [org] [bucket]
# Ensure the input file is passed as a parameter.

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <input_file> [org] [bucket]"
  exit 1
fi

# Parameters
INPUT_FILE="$1"
INFLUX_URL="https://us-east-1-1.aws.cloud2.influxdata.com"
INFLUX_ORG="${2:-DSN}"      # Default to "DSN" if not provided
INFLUX_BUCKET="${3:-TEST}"  # Default to "TEST" if not provided
INFLUX_TOKEN="${INFLUX_TOKEN:-}"  # Use environment variable or empty if not set
ERROR_FILE="errors.log"

# Check if the input file exists
if [ ! -f "$INPUT_FILE" ]; then
  echo "Error: File '$INPUT_FILE' not found."
  exit 1
fi

# Check if the InfluxDB token is set
if [ -z "$INFLUX_TOKEN" ]; then
  echo "Error: INFLUX_TOKEN is not set. Set it as an environment variable or include it in the script."
  exit 1
fi

# Normalize the input file's line endings and encoding
echo "Normalizing file: $INPUT_FILE"
dos2unix "$INPUT_FILE"
iconv -f UTF-8 -t UTF-8 "$INPUT_FILE" -o "$INPUT_FILE"

# Write data to InfluxDB
echo "Writing data to InfluxDB..."
influx write \
  --url "$INFLUX_URL" \
  --org "$INFLUX_ORG" \
  --bucket "$INFLUX_BUCKET" \
  --token "$INFLUX_TOKEN" \
  --file "$INPUT_FILE" \
  --format csv \
  --skipRowOnError \
  --errors-file "$ERROR_FILE"

# Check for errors
if [ -s "$ERROR_FILE" ]; then
  echo "Errors occurred during the write operation:"
  cat "$ERROR_FILE"
else
  echo "Data successfully written to InfluxDB."
fi
