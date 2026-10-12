"""Capture a disposable, unexposed Docker demo; never touch an existing name.

Run explicitly with --execute. Requires Docker CLI access. No host volumes,
published ports, privileged mode, or application workload changes are used.
"""
import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        parser.error('Pass --execute to create and clean up the disposable demo container')
    probe = subprocess.run(['docker', 'container', 'inspect', 'demo'], capture_output=True)
    if probe.returncode == 0:
        raise SystemExit('Container demo already exists; refusing to alter it')
    subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], check=True, capture_output=True)
    captured = []
    container_id = None

    def run(command):
        result = subprocess.run(command, text=True, capture_output=True, check=True, timeout=120)
        captured.append({'command': command, 'stdout': result.stdout, 'stderr': result.stderr})
        return result.stdout.strip()

    try:
        container_id = run(['docker', 'run', '--name', 'demo', '-d', 'nginx:alpine'])
        # Restrict the captured listing to our own ID, never unrelated workloads.
        run(['docker', 'ps', '--filter', 'id=' + container_id, '--format', '{{.Image}} | {{.Status}} | {{.Names}}'])
        run(['docker', 'logs', 'demo'])
        run(['docker', 'stop', 'demo'])
        run(['docker', 'rm', 'demo'])
        container_id = None
    finally:
        if container_id:
            # Only the ID returned by this invocation is eligible for cleanup.
            subprocess.run(['docker', 'rm', '-f', container_id], check=True, capture_output=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(captured, indent=2) + '\n')


if __name__ == '__main__':
    main()
