"""Run both applications in one CPU-only container and preserve device evidence."""
import argparse
import os
from pathlib import Path
import re
import subprocess

from .benchmark import run, save


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, default=Path('artifacts/cpu-summary'))
    args = parser.parse_args(argv)
    binary = Path('.tools/hashcat/hashcat-7.1.2/hashcat.bin').resolve()
    command = [str(binary), '--backend-ignore-cuda', '--backend-ignore-hip', '-D', '1', '-I']
    device = subprocess.run(command, cwd=binary.parent, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=30, check=False)
    evidence = device.stdout + device.stderr
    if device.returncode:
        raise RuntimeError(evidence)
    if not re.search(r'Type\.+:\s*CPU', evidence) or re.search(r'Type\.+:\s*GPU', evidence):
        raise RuntimeError('Expected CPU-only OpenCL device; refusing to record non-CPU measurements')
    print(evidence, flush=True)
    report = run(args.repeats, True, str(binary), True, 'threads', (1,), 'cpu')
    report['hashcat_environment'] = evidence
    report['cpu_affinity'] = sorted(os.sched_getaffinity(0))
    report['pocl_max_pthread_count'] = os.environ.get('POCL_MAX_PTHREAD_COUNT')
    if len(report['cpu_affinity']) != 1:
        raise RuntimeError('Expected one logical CPU shared by both applications')
    if not all(row.get('device_type') == 'cpu' and row.get('supported') and row.get('cracked')
               for row in report['professional']):
        args.output.mkdir(parents=True, exist_ok=True)
        save(report, args.output)
        raise RuntimeError('CPU hashcat did not verify every test hash; see results.json')
    save(report, args.output)
    print(f'CPU measurements saved to {args.output}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
