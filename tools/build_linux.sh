#!/usr/bin/env bash
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$project_dir"
python_bin=${PYTHON_BIN:-python3.11}
output_dir=${1:-dist/developer-sdk-linux}
if [ -e "$output_dir" ]; then
    printf '输出目录已存在：%s\n' "$output_dir" >&2
    exit 1
fi
"$python_bin" setup.py build_ext --force --build-lib build/protected-linux --build-temp build/temp-linux
"$python_bin" tools/export_developer_package.py --binary-dir build/protected-linux --output "$output_dir"
