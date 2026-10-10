"""Запуск hashcat на том же наборе кандидатов и проверка результата."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from .candidates import iter_candidates
from .hashes import HashTarget
from .models import CrackConfig
from .wordlist import inspect_wordlist


HASHCAT_MODES = {"md5": "0", "sha1": "100", "bcrypt": "3200", "argon2id": "34000"}


def compare_hashcat(target: HashTarget, config: CrackConfig, executable: str = "hashcat", device_type: str = "auto",
                    attack: str = 'generated-wordlist', wordlist: Path | None = None) -> dict[str, object]:
    if device_type not in ('auto', 'cpu', 'gpu'):
        raise ValueError('hashcat device must be auto, cpu or gpu')
    if attack not in ('generated-wordlist', 'mask', 'wordlist'):
        raise ValueError('Unknown hashcat attack')
    if attack == 'wordlist' and wordlist is None:
        raise ValueError('Dictionary attack requires a wordlist')
    if attack == 'mask' and (config.min_length != config.max_length or not (config.alphabet + config.prefix).isascii()):
        raise ValueError('Hashcat mask comparison requires a fixed length and ASCII charset/prefix')
    binary = shutil.which(executable)
    if binary is None:
        return {"available": False, "reason": "hashcat is not installed", "elapsed_seconds": None}
    binary = str(Path(binary).resolve())
    mode = HASHCAT_MODES.get(target.algorithm)
    if mode is None:
        return {"available": False, "reason": f"No verified hashcat mode configured for {target.algorithm}", "elapsed_seconds": None}
    config.validate()
    scratch = Path(__file__).resolve().parents[2] / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lab3-hashcat-", dir=scratch) as directory:
        target_file = Path(directory) / "target.hash"
        input_file = Path(directory) / "candidates.txt"
        cracked_file = Path(directory) / "cracked.txt"
        target_file.write_text(target.encoded + "\n", encoding="ascii")
        if attack == 'generated-wordlist':
            with input_file.open("w", encoding="utf-8", newline="\n") as output:
                for candidate in iter_candidates(config):
                    output.write(candidate + "\n")
        elif attack == 'wordlist':
            input_file = wordlist.resolve(strict=True)
            inspect_wordlist(input_file)
        mask = config.prefix.replace('?', '??') + '?1' * config.max_length
        command = [
            binary,
            "--quiet",
            "--potfile-disable",
            "--restore-disable",
            "--logfile-disable",
            "--outfile", str(cracked_file),
            "--outfile-format", "2",
            "-m", mode,
            "-a", "3" if attack == 'mask' else "0",
            str(target_file),
            mask if attack == 'mask' else str(input_file),
        ]
        if attack == 'mask':
            command[1:1] = ['-1', config.alphabet, '--markov-disable']
        elif attack == 'wordlist':
            command[1:1] = ['--wordlist-autohex-disable', '--outfile-autohex-disable']
        device_args = []
        if device_type == 'cpu':
            device_args = ['--backend-ignore-cuda', '--backend-ignore-hip', '-D', '1']
        elif device_type == 'gpu':
            device_args = ['--backend-ignore-cuda', '--backend-ignore-hip', '-D', '2', '-d', '1']
        command[1:1] = device_args
        started = time.perf_counter()
        process = subprocess.run(command, cwd=Path(binary).parent, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=300, check=False)
        elapsed = time.perf_counter() - started
        output_text = process.stdout + process.stderr
        if process.returncode not in (0, 1):
            return {"available": True, "supported": False, "reason": output_text.strip()[-1000:], "elapsed_seconds": elapsed,
                    "device_type": device_type}
        return {
            "available": True,
            "supported": True,
            "cracked": cracked_file.exists() and any(target.matches(line) for line in cracked_file.read_text(encoding='utf-8').splitlines()),
            "elapsed_seconds": elapsed,
            "device_type": device_type,
            "attack": attack,
            "command": f"hashcat {' '.join(device_args)} --potfile-disable --restore-disable --logfile-disable -m {mode} -a "
                       + ('3 -1 '+config.alphabet+' --markov-disable target.hash '+mask if attack == 'mask' else '0 target.hash '+('rockyou.txt' if attack == 'wordlist' else 'candidates.txt')),
        }

