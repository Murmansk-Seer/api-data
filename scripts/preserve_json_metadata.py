"""Keep original metadata bytes when only build time and its hash changed."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def semantic_metadata(data):
    return json.dumps({k: v for k, v in data.items() if k not in ('generate_time', 'hash')}, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def preserve_metadata(base=Path('data'), version='v1'):
    if version in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', version):
        raise ValueError('Invalid API version')
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
    preserved = []
    for kind in ('data', 'sharded_data', 'schemas'):
        path = base / version / kind / 'metadata.json'
        if not path.is_file():
            continue
        relative = path.resolve().relative_to(root).as_posix()
        previous = subprocess.run(['git', 'show', 'HEAD:' + relative], capture_output=True)
        if previous.returncode:
            continue
        old = json.loads(previous.stdout)
        current = json.loads(path.read_text(encoding='utf-8'))
        if semantic_metadata(current) == semantic_metadata(old):
            path.write_bytes(previous.stdout)
            preserved.append(relative)
    return preserved


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-output-dir', type=Path, default=Path('data'))
    parser.add_argument('--api-version', default='v1')
    args = parser.parse_args()
    print(json.dumps(preserve_metadata(args.base_output_dir, args.api_version)))
