"""Only verified releases advance the published source fingerprint."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

STATE = Path('.build-state/publication.json')
ACK = Path('.build-state/notified-fingerprint')


def fingerprint(config, patch):
    digest = hashlib.sha256((config + '\n' + patch).encode())
    for path in sorted([Path('.github/workflows/main.yml'), *Path('scripts').glob('*.py')]):
        digest.update(path.as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def check(config, patch, force=False):
    current = fingerprint(config, patch)
    previous = load_state()
    skip = not force and previous.get('fingerprint') == current
    acknowledged = ACK.read_text().strip() if ACK.exists() else ''
    return {
        'config_head': config, 'patch_head': patch, 'fingerprint': current,
        'skip': str(skip).lower(),
        'notify': str(skip and acknowledged != current).lower(),
        'published_sha': previous.get('sha256', ''),
        'published_commit': previous.get('source_commit', ''),
    }


def validate_database(path, expected=None):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected and digest != expected:
        raise ValueError('Release SHA256 differs from generated database')
    with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Database integrity_check failed')
    return digest


def verify_release(expected):
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(['gh', 'release', 'download', 'latest', '--repo', os.environ['GITHUB_REPOSITORY'],
                        '--pattern', 'seerapi-data.sqlite*', '--dir', directory], check=True)
        root = Path(directory)
        recorded = (root / 'seerapi-data.sqlite.sha256').read_text().split()[0]
        if recorded != expected:
            raise ValueError('Release checksum asset mismatch')
        validate_database(root / 'seerapi-data.sqlite', expected)


def record(config, patch, digest, revision, expected_fingerprint):
    # Called only after upload and remote verification. The workflow gates this
    # command on those steps succeeding; failure leaves the old state untouched.
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid verified release digest')
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(dict(config=config, patch=patch, sha256=digest,
                                    source_commit=revision, fingerprint=expected_fingerprint), indent=2) + '\n')
    Path('.build-state/config-sources-revision').write_text(config + '\n')
    Path('.build-state/patch-sources-revision').write_text(patch + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['check', 'validate', 'verify', 'record', 'ack'])
    args = parser.parse_args()
    if args.command == 'check':
        result = check(os.environ['CONFIG_HEAD'], os.environ['PATCH_HEAD'], os.environ.get('FORCE') == 'true')
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
            for key, value in result.items():
                output.write(f'{key}={value}\n')
    elif args.command == 'validate':
        print(validate_database(Path('seerapi-data.sqlite')))
    elif args.command == 'verify':
        verify_release(os.environ['DB_SHA'])
    elif args.command == 'record':
        record(os.environ['CONFIG_HEAD'], os.environ['PATCH_HEAD'], os.environ['DB_SHA'],
               os.environ['DATA_COMMIT'], os.environ['BUILD_FINGERPRINT'])
    else:
        state = load_state()
        ACK.write_text(state['fingerprint'] + '\n')


if __name__ == '__main__':
    main()
