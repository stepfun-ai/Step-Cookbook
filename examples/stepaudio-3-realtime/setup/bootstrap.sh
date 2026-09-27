#!/bin/bash
# 所有运行时与缓存均保存在这份包中，不依赖系统 Python。
set -eu
cd -- "$(dirname -- "$0")/.."
package_dir="$(pwd -P)"
if [ "$(uname -s)" != Darwin ]; then
  printf '此入口适用于 macOS。Windows 请双击 启动.bat。\n' >&2
  exit 1
fi
case "$(uname -m)" in
  arm64)
    target=aarch64-apple-darwin
    expected_sha=a9a8df1eedeb192f2e47e40e2faabfb387db4b850209118786d42f89dde3e0ba ;;
  x86_64)
    target=x86_64-apple-darwin
    expected_sha=cb5fa57bafe68fc0fb94b17f06bee0b0b9a7feb94ccbd110445afa0696e39273 ;;
  *) printf '暂不支持这台 Mac 的处理器架构。\n' >&2; exit 1 ;;
esac
runtime_dir="$package_dir/.runtime"
uv_bin="$runtime_dir/uv-$target/uv"
mkdir -p "$runtime_dir"
if [ ! -x "$uv_bin" ]; then
  printf '[1/3] 下载环境管理器 uv 0.12.19……\n'
  stage_dir="$(mktemp -d "$runtime_dir/download.XXXXXX")"
  trap 'rm -rf -- "$stage_dir"' EXIT
  curl --fail --location --retry 2 --connect-timeout 15 --max-time 300 \
    "https://github.com/astral-sh/uv/releases/download/0.12.19/uv-$target.tar.gz" \
    --output "$stage_dir/uv.tar.gz"
  actual_sha="$(shasum -a 256 "$stage_dir/uv.tar.gz" | awk '{print $1}')"
  if [ "$actual_sha" != "$expected_sha" ]; then
    printf '下载校验未通过，请再次启动以重新下载。\n' >&2
    exit 1
  fi
  tar -xzf "$stage_dir/uv.tar.gz" -C "$stage_dir"
  mv "$stage_dir/uv-$target" "$runtime_dir/uv-$target"
  rm -rf -- "$stage_dir"
  trap - EXIT
fi
export UV_CACHE_DIR="$runtime_dir/cache"
export UV_PYTHON_INSTALL_DIR="$runtime_dir/python"
export UV_PYTHON_BIN_DIR="$runtime_dir/bin"
export UV_NO_CONFIG=1 UV_NO_PROGRESS=1 UV_HTTP_TIMEOUT=120 UV_HTTP_RETRIES=2
export PYTHONUTF8=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
python_bin="$package_dir/.venv/bin/python"
if [ ! -x "$python_bin" ] || ! "$python_bin" setup/check_env.py --quiet; then
  printf '[2/3] 准备专用 Python 3.12.14 和虚拟环境……\n'
  if [ -e .venv ]; then
    # 旧环境留存，便于恢复；移动目录后由新的绝对路径重新建立环境。
    previous_env="$(mktemp -d "$runtime_dir/previous-env.XXXXXX")"
    mv .venv "$previous_env/venv"
  fi
  "$uv_bin" venv --no-project --managed-python --python 3.12.14 .venv
  printf '[3/3] 准备本篇所需依赖……\n'
  if [ -s setup/requirements.lock ]; then
  "$uv_bin" pip sync --python "$python_bin" --require-hashes \
    --only-binary :all: --default-index https://pypi.org/simple setup/requirements.lock
  else
    printf '本篇仅使用 Python 标准库，环境已齐全。\n'
  fi
  "$python_bin" setup/check_env.py --mark
else
  printf '环境已就绪，复用本地 Python 与依赖。\n'
fi
if [ "${1:-}" = --setup-only ]; then
  "$python_bin" setup/check_env.py
  exit 0
fi
"$python_bin" launcher.py
