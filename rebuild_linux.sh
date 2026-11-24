#!/usr/bin/env bash
set -euo pipefail

project_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python_bin="$HOME/.venvs/robot-cal/bin/python"
releases_dir="$HOME/robot-cal-builds"
latest_link="$HOME/robot-cal-latest"
archive_name=developer-sdk-linux.tar.gz
archive_path="$project_dir/$archive_name"

if [[ $(uname -s) != Linux ]]; then
    printf '请在 Linux 中运行此脚本。\n' >&2
    exit 1
fi
if [[ ! -x "$python_bin" ]]; then
    printf '未找到 Python 虚拟环境：%s\n' "$python_bin" >&2
    exit 1
fi
if [[ -e "$latest_link" && ! -L "$latest_link" ]]; then
    printf '固定入口已存在且不是符号链接：%s\n' "$latest_link" >&2
    exit 1
fi

mkdir -p -- "$releases_dir"
exec 9>"$releases_dir/.rebuild.lock"
if ! flock -n 9; then
    printf '已有 Linux 编译任务正在运行。\n' >&2
    exit 1
fi

release_dir=$(mktemp -d "$releases_dir/$(date +%Y%m%d-%H%M%S).XXXXXX")
package_dir="$release_dir/developer-sdk-linux"
PYTHON_BIN="$python_bin" bash "$project_dir/tools/build_linux.sh" "$package_dir"
(cd -- "$package_dir" && "$python_bin" -B main.py --check-deployment)

# 在目标文件所在的文件系统上完成归档，再替换正式文件。
archive_stage=$(mktemp -d "$project_dir/.linux-archive.XXXXXX")
trap 'rm -f -- "$archive_stage/$archive_name"; rmdir -- "$archive_stage"' EXIT
tar -C "$release_dir" -czf "$archive_stage/$archive_name" developer-sdk-linux
tar -tzf "$archive_stage/$archive_name" >/dev/null
mv -fT -- "$archive_stage/$archive_name" "$archive_path"
ln -sfnT -- "$package_dir" "$latest_link"

printf '已更新归档：%s\n运行目录：%s\n' "$archive_path" "$latest_link"
