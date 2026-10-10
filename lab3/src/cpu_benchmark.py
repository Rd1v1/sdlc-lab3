"""Run both applications in one CPU-only container and preserve device evidence."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from .benchmark import run, save
from .dictionary_benchmark import run as run_dictionary, render_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, default=Path('artifacts/cpu-summary'))
    parser.add_argument('--comparison', choices=('legacy', 'dictionary'), default='dictionary')
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
    if args.comparison == 'dictionary':
        wordlist = Path('.tools/wordlists/rockyou.txt').resolve()
        report = run_dictionary(args.repeats, str(binary), wordlist)
        source = wordlist.with_name('rockyou-source.json')
        if source.exists():
            report['dictionary_source'] = json.loads(source.read_text(encoding='utf-8'))
    else:
        report = run(args.repeats, True, str(binary), True, 'threads', (1,), 'cpu')
    report['hashcat_environment'] = evidence
    report['cpu_affinity'] = sorted(os.sched_getaffinity(0))
    report['pocl_max_pthread_count'] = os.environ.get('POCL_MAX_PTHREAD_COUNT')
    if len(report['cpu_affinity']) != 1:
        raise RuntimeError('Expected one logical CPU shared by both applications')
    if not all(row.get('device_type') == 'cpu' and row.get('supported') and row.get('cracked')
               for row in report['professional']):
        args.output.mkdir(parents=True, exist_ok=True)
        if args.comparison == 'legacy':
            save(report, args.output)
        raise RuntimeError('CPU hashcat did not verify every test hash; see results.json')
    if args.comparison == 'dictionary':
        import csv
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        for name, rows in (('results.csv', report['results']), ('hashcat-runs.csv', report['professional'])):
            with (args.output/name).open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        (args.output/'analysis.md').write_text(render_report(report), encoding='utf-8')
    else:
        save(report, args.output)
    print(f'CPU measurements saved to {args.output}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
