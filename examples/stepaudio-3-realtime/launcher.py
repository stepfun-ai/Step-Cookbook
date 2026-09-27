"""仅运行本目录这一篇 Demo。"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROFILE = json.loads((ROOT / 'setup/profile.json').read_text(encoding='utf-8'))


def main():
    region = os.environ.get('STEPFUN_REGION', 'cn')
    if region not in ('cn', 'global'):
        region = 'cn'
    print('\n' + PROFILE['title'] + ' · 独立运行版')
    print('本篇环境已就绪。选择运行后才连接模型并使用账户额度。')
    while True:
        print('\n站点：' + ('中国站 .com' if region == 'cn' else '国际站 .ai'))
        print('  1. 最小示例（默认）：' + PROFILE['minimal'])
        print('  2. 完整实验：' + PROFILE['full'])
        print('  R. 切换站点    0. 退出')
        choice = input('请选择 [1]：').strip().lower() or '1'
        if choice == '0':
            return
        if choice == 'r':
            region = 'global' if region == 'cn' else 'cn'
            continue
        if choice not in ('1', '2'):
            print('请输入 1、2、R 或 0。')
            continue
        if PROFILE['id'].startswith('04_'):
            print('请连接麦克风与耳机，并按系统提示允许终端访问麦克风。')
        command = [sys.executable, str(ROOT / PROFILE['script'])]
        if choice == '2':
            command.append('--full')
        try:
            status = subprocess.run(command, cwd=ROOT,
                env={**os.environ, 'STEPFUN_REGION': region}).returncode
            print('运行结束，结果目录见上方。' if status == 0 else '本次已停止，请查看上方提示。')
        except KeyboardInterrupt:
            print('\n已中止本次运行。')


if __name__ == '__main__':
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print('\n已退出。')
