"""仅检查环境与素材；不会请求模型，也不会打开麦克风。"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = ROOT / '.runtime' / 'ready.json'
PROFILE = json.loads((ROOT / 'setup/profile.json').read_text(encoding='utf-8'))
VERSIONS = PROFILE['dependencies']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def inspect(mark=False):
    require(sys.version_info[:3] == (3, 12, 14), '需要本包专用 Python 3.12.14')
    require(Path(sys.prefix).resolve() == (ROOT / '.venv').resolve(), '需要本包虚拟环境')
    require(Path(sys.base_prefix).resolve().is_relative_to(ROOT / '.runtime'), '运行时路径已变化')
    for name, version in VERSIONS.items():
        require(importlib.metadata.version(name) == version, name + ' 版本不符')
    if 'sounddevice' in VERSIONS:
        import websocket
        import sounddevice
        sounddevice.get_portaudio_version()
    for asset in PROFILE['assets']:
        require((ROOT / 'assets' / asset).is_file(), '缺少随包素材：' + asset)
    state = {'profile': PROFILE['id'], 'root': str(ROOT), 'python': platform.python_version(),
             'dependencies': VERSIONS, 'requirements_sha256': hashlib.sha256(
                 (ROOT / 'setup/requirements.lock').read_bytes()).hexdigest()}
    if mark:
        STAMP.parent.mkdir(exist_ok=True)
        STAMP.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        require(STAMP.exists() and json.loads(STAMP.read_text(encoding='utf-8')) == state, '需要准备当前目录的环境')
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--mark', action='store_true')
    args = parser.parse_args()
    try:
        state = inspect(args.mark)
        if not args.quiet:
            print('环境就绪：Python ' + state['python'] + '，依赖与随包素材齐全。')
    except Exception as exc:
        if not args.quiet:
            print('环境待准备：' + str(exc))
        sys.exit(1)
