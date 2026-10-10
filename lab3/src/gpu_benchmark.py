"""Run the native Windows GPU hashcat comparison and record device evidence."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

from .dictionary_benchmark import run, render_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, default=Path('artifacts/gpu-summary'))
    args = parser.parse_args(argv)
    binary = Path('.tools/hashcat/hashcat-7.1.2/hashcat.exe').resolve()
    device = subprocess.run([str(binary), '--backend-ignore-cuda', '--backend-ignore-hip', '-D', '2', '-d', '1', '-I'], cwd=binary.parent,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, check=True)
    evidence = device.stdout + device.stderr
    if len(re.findall(r'Type\.+:\s*GPU', evidence)) != 1:
        raise RuntimeError('No GPU device detected; refusing to record GPU measurements')
    wordlist = Path('.tools/wordlists/rockyou.txt').resolve()
    report = run(args.repeats, str(binary), wordlist, 'gpu')
    report['hashcat_environment'] = evidence
    report['dictionary_source'] = json.loads(wordlist.with_name('rockyou-source.json').read_text(encoding='utf-8'))
    if not all(row.get('device_type') == 'gpu' and row.get('supported') and row.get('cracked') for row in report['professional']):
        raise RuntimeError('GPU hashcat did not verify every test hash')
    if not all(row['backend'] == 'gpu' and row['gpu_device']['type'] == 'GPU'
               and row['gpu_device']['name'] in evidence for row in report['results']):
        raise RuntimeError('Applications did not use the same verified GPU')
    report['gpu_device'] = report['results'][0]['gpu_device']
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for filename, rows in (('results.csv', report['results']), ('hashcat-runs.csv', report['professional'])):
        with (args.output/filename).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (args.output/'analysis.md').write_text(render_report(report), encoding='utf-8')
    print('GPU comparison saved to', args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
