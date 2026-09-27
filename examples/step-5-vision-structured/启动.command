#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
if ! /bin/bash setup/bootstrap.sh "$@"; then
  printf '\n启动未完成。请查看上方提示，处理后再次双击即可继续。\n'
  if [ -t 0 ]; then read -r -p '按 Enter 关闭窗口……' _reply; fi
  exit 1
fi
