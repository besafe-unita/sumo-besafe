#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

CARPM="${1:-5}"
BIKEPM="${2:-3}"

rate_label() {
    printf "%s" "$1" | sed 's/\./p/g'
}

CAR_LABEL="$(rate_label "${CARPM}")"
BIKE_LABEL="$(rate_label "${BIKEPM}")"
PREFIX="car${CAR_LABEL}vpm_bike${BIKE_LABEL}vpm"

python3 "${ROOT_DIR}/bin/gendemand.py" \
    --carpm "${CARPM}" \
    --bikepm 0 \
    --safefraction 0.0 \
    --outname "${PREFIX}_autoonly.rou.xml"

python3 "${ROOT_DIR}/bin/gendemand.py" \
    --carpm "${CARPM}" \
    --bikepm "${BIKEPM}" \
    --safefraction 1.0 \
    --outname "${PREFIX}_safety.rou.xml"

python3 "${ROOT_DIR}/bin/gendemand.py" \
    --carpm "${CARPM}" \
    --bikepm "${BIKEPM}" \
    --safefraction 0.0 \
    --outname "${PREFIX}_risky.rou.xml"

python3 "${ROOT_DIR}/bin/gendemand.py" \
    --carpm "${CARPM}" \
    --bikepm "${BIKEPM}" \
    --safefraction 0.7 \
    --outname "${PREFIX}_safe70risky30.rou.xml"
