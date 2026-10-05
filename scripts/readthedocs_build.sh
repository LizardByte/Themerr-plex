#!/usr/bin/env bash
set -euo pipefail

# Follow Themerr-jellyfin's Dockle bootstrap: create Conda before invoking uv.
environment_name="${READTHEDOCS_VERSION:-dockle-docs}"
conda env create --quiet --name "${environment_name}" --file docs/environment.yml

uv_run=(conda run --no-capture-output --name "${environment_name}" uv)
"${uv_run[@]}" sync --locked --extra docs --no-install-project --no-build \
  --no-python-downloads --python 3.14

dockle_run=("${uv_run[@]}" run --no-sync python)
"${dockle_run[@]}" scripts/localize.py --compile
"${dockle_run[@]}" -m dockle check
"${dockle_run[@]}" -m dockle build

mkdir -p "${READTHEDOCS_OUTPUT}html/"
cp -r _site/. "${READTHEDOCS_OUTPUT}html/"
