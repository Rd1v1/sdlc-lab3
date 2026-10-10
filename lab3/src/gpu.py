"""Independent PyOpenCL host engine; no hashcat process is used by this module."""
from __future__ import annotations
import base64
import itertools
import os
from pathlib import Path
import re
import tempfile
import time

from .candidates import iter_candidates
from .hashes import HashTarget
from .models import WorkerProgress
from .wordlist import inspect_wordlist


ROOT = Path(__file__).resolve().parents[2]
KERNELS = Path(__file__).with_name('kernels')


def _source(names):
    seen = set()
    def expand(name):
        if name in seen:
            return ''
        seen.add(name)
        path = KERNELS/'vendor'/name
        text = path.read_text(encoding='utf-8')
        return re.sub(r'^\s*#include\s+"([^"\n]+)"', lambda match: expand(match[1]), text, flags=re.M)
    return '\n'.join(expand(name) for name in names)


def _bcrypt_decode(text):
    alphabet = './ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    accumulator = bits = 0
    output = bytearray()
    for char in text:
        accumulator = (accumulator << 6) | alphabet.index(char)
        bits += 6
        if bits >= 8:
            bits -= 8
            output.append((accumulator >> bits) & 255)
    return bytes(output)


class GpuHasher:
    def __init__(self, target: HashTarget, device_index=0):
        cache = ROOT/'.cache/pyopencl'
        scratch = ROOT/'.tmp/gpu'
        driver_cache = ROOT/'.cache/nvidia'
        for directory in (cache, scratch, driver_cache):
            directory.mkdir(parents=True, exist_ok=True)
        def native_path(path):
            if os.name != 'nt':
                return str(path)
            import ctypes
            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
            return buffer.value if 0 < length < len(buffer) else str(path)
        tempfile.tempdir = native_path(scratch)
        for key in ('TEMP', 'TMP', 'TMPDIR'):
            os.environ[key] = tempfile.tempdir
        os.environ['PYOPENCL_CACHE_DIR'] = native_path(cache)
        os.environ['CUDA_CACHE_PATH'] = native_path(driver_cache)
        try:
            import numpy as np
            import pyopencl as cl
        except ImportError as error:
            raise RuntimeError('Установите requirements.txt в проектную .venv') from error
        parsed = HashTarget.parse(target.encoded)
        if parsed.algorithm != target.algorithm:
            raise ValueError('Алгоритм не соответствует хэшу')
        target = parsed
        self.cl, self.np, self.target = cl, np, target
        devices = [device for platform in cl.get_platforms() for device in platform.get_devices()
                   if device.type & cl.device_type.GPU]
        if not 0 <= device_index < len(devices):
            raise RuntimeError('Указанная GPU недоступна; CPU fallback отключён')
        self.device = devices[device_index]
        self.context = cl.Context([self.device])
        self.queue = cl.CommandQueue(self.context, properties=cl.command_queue_properties.PROFILING_ENABLE)
        self.kernel_seconds = 0.0
        self.events = []
        self.memory_per_candidate = 0
        names = ['inc_platform.cl', 'inc_common.cl']
        algorithm = target.algorithm
        if algorithm in ('md5', 'sha1'):
            names += ['inc_hash_md5.cl', 'inc_hash_sha1.cl']
            wrapper = (KERNELS/'fast.cl').read_text(encoding='utf-8')
            self.expected = bytes.fromhex(target.encoded)
        elif algorithm == 'bcrypt':
            names += ['inc_cipher_blowfish.cl']
            wrapper = (KERNELS/'bcrypt.cl').read_text(encoding='utf-8')
            self.salt_bytes = _bcrypt_decode(target.encoded[7:29])
            self.expected = _bcrypt_decode(target.encoded[29:])
            self.cost = int(target.encoded[4:6])
        else:
            names += ['inc_hash_blake2b.cl', 'inc_hash_argon2.cl']
            wrapper = (KERNELS/'argon2.cl').read_text(encoding='utf-8')
            parts = target.encoded.split('$')
            parameters = dict(item.split('=') for item in parts[3].split(','))
            self.memory_kib, self.iterations, self.parallelism = [int(parameters[name]) for name in ('m', 't', 'p')]
            self.salt_bytes = base64.b64decode(parts[4]+'='*(-len(parts[4]) % 4))
            self.expected = base64.b64decode(parts[5]+'='*(-len(parts[5]) % 4))
            if len(self.expected) != 32:
                raise ValueError('GPU Argon2id поддерживает 32-байтовый digest; используйте CPU для других длин')
            segment = self.memory_kib // (4 * self.parallelism)
            blocks = segment * 4 * self.parallelism
            self.memory_per_candidate = blocks * 1024
            self.options = np.array([2, 19, self.iterations, self.parallelism, self.memory_kib,
                                     segment, segment * 4, blocks, 32], dtype=np.uint32)
        options = ['-DDEVICE_TYPE=4', '-DVENDOR_ID=32' if 'NVIDIA' in self.device.vendor else '-DVENDOR_ID=0',
                   '-DLOCAL_MEM_TYPE=1', '-DVECT_SIZE=1', '-DKERNEL_STATIC', '-DDGST_ELEM=16', '-DFIXED_LOCAL_SIZE=8',
                   '-DDGST_R0=0', '-DDGST_R1=1', '-DDGST_R2=2', '-DDGST_R3=3']
        self.program = cl.Program(self.context, _source(names)+'\n'+wrapper).build(options=options, cache_dir=native_path(cache))
        self.kernels = {name: cl.Kernel(self.program, name) for name in
                        (('md5_batch', 'sha1_batch') if algorithm in ('md5', 'sha1') else
                         ('bcrypt_init', 'bcrypt_loop', 'bcrypt_final') if algorithm == 'bcrypt' else
                         ('argon_init', 'argon_segment', 'argon_final'))}

    def device_info(self):
        return {'name': self.device.name, 'vendor': self.device.vendor, 'driver': self.device.driver_version,
                'type': 'GPU', 'platform': self.device.platform.name}

    def _launch(self, name, shape, local, *args):
        event = self.kernels[name](self.queue, shape, local, *args)
        self.events.append(event)
        return event

    def digest_batch(self, candidates):
        cl, np = self.cl, self.np
        count = len(candidates)
        if not count:
            return []
        if any(len(candidate) > 256 for candidate in candidates):
            raise ValueError('GPU: максимум 256 байт на кандидата')
        if self.target.algorithm == 'bcrypt' and any(len(candidate) > 72 for candidate in candidates):
            raise ValueError('bcrypt: максимум 72 байта на кандидата')
        pws = np.zeros((count, 65), dtype=np.uint32)
        for row, candidate in enumerate(candidates):
            padded = candidate + b'\0' * (256 - len(candidate))
            pws[row, :64] = np.frombuffer(padded, dtype='<u4')
            pws[row, 64] = len(candidate)
        flags = cl.mem_flags
        buffers = []
        def upload(data):
            buf = cl.Buffer(self.context, flags.READ_ONLY | flags.COPY_HOST_PTR, hostbuf=data)
            buffers.append(buf)
            return buf
        def allocate(size):
            if size > self.device.max_mem_alloc_size:
                raise ValueError('GPU allocation exceeds device limit; reduce --gpu-batch-size')
            buf = cl.Buffer(self.context, flags.READ_WRITE, size=size)
            buffers.append(buf)
            return buf
        self.events = []
        try:
            passwords = upload(pws)
            output = np.zeros((count, 8), dtype=np.uint32)
            gpu_output = allocate(output.nbytes)
            number = np.uint32(count)
            algorithm = self.target.algorithm
            if algorithm in ('md5', 'sha1'):
                self._launch(algorithm+'_batch', (count,), None, passwords, gpu_output, number)
            elif algorithm == 'bcrypt':
                salt = np.zeros(143, dtype=np.uint32)
                salt[:4] = np.frombuffer(self.salt_bytes, dtype='>u4')
                gpu_salt = upload(salt)
                temporaries = allocate(count * 1060 * 4)
                shape = ((count + 7) // 8 * 8,)
                args = (passwords, temporaries, gpu_salt, number)
                self._launch('bcrypt_init', shape, (8,), *args, np.uint32(0))
                rounds = 1 << self.cost
                for position in range(0, rounds, 64):
                    self._launch('bcrypt_loop', shape, (8,), *args, np.uint32(min(64, rounds - position)))
                self._launch('bcrypt_final', shape, (8,), *args, np.uint32(0), gpu_output)
            else:
                salt = np.zeros(143, dtype=np.uint32)
                raw_salt = self.salt_bytes + b'\0' * (256 - len(self.salt_bytes))
                salt[:64] = np.frombuffer(raw_salt, dtype='<u4')
                salt[128] = len(self.salt_bytes)
                gpu_salt = upload(salt)
                gpu_options = upload(self.options)
                memory = allocate(count * self.memory_per_candidate)
                self._launch('argon_init', (count,), None, passwords, gpu_salt, gpu_options, memory, number)
                for iteration in range(self.iterations):
                    for segment in range(4):
                        self._launch('argon_segment', (count * 32, self.parallelism), (32, self.parallelism),
                                     gpu_options, memory, number, np.uint32(iteration), np.uint32(segment))
                self._launch('argon_final', (count,), None, gpu_options, memory, gpu_output, number)
            cl.enqueue_copy(self.queue, output, gpu_output).wait()
            self.kernel_seconds += sum((event.profile.end - event.profile.start) / 1e9 for event in self.events)
            if algorithm == 'md5':
                return [row[:4].astype('<u4').tobytes() for row in output]
            if algorithm == 'sha1':
                return [row[:5].astype('>u4').tobytes() for row in output]
            if algorithm == 'bcrypt':
                return [row[:6].astype('>u4').tobytes()[:23] for row in output]
            return [row.astype('<u4').tobytes() for row in output]
        finally:
            self.queue.finish()
            for buf in reversed(buffers):
                buf.release()


def search_gpu(target, config, wordlist=None, batch_size=16, device_index=0, on_progress=None):
    if not 1 <= batch_size <= 4096:
        raise ValueError('GPU batch size must be 1..4096')
    config.validate()
    started = time.perf_counter()
    hasher = GpuHasher(target, device_index)
    if hasher.memory_per_candidate:
        safe = min(32, hasher.device.max_mem_alloc_size // hasher.memory_per_candidate,
                   hasher.device.global_mem_size // (4 * hasher.memory_per_candidate))
        if batch_size > safe:
            raise ValueError(f'Argon2id: уменьшите --gpu-batch-size до {safe}')
    file_handle = None
    total = config.validate()
    if wordlist is None:
        candidates = (candidate.encode('utf-8') for candidate in iter_candidates(config))
    else:
        total = inspect_wordlist(wordlist)['lines']
        file_handle = wordlist.open('rb')
        candidates = (line.removesuffix(b'\n').removesuffix(b'\r') for line in file_handle)
    checked = rejected = 0
    try:
        while batch := list(itertools.islice(candidates, batch_size)):
            limit = 72 if target.algorithm == 'bcrypt' else 256
            valid = [(index, candidate) for index, candidate in enumerate(batch) if len(candidate) <= limit]
            rejected += len(batch) - len(valid)
            if on_progress:
                on_progress(tuple(WorkerProgress(index + 1, candidate.decode('utf-8', errors='backslashreplace'),
                                                  0, 'running') for index, candidate in enumerate(batch)))
            outputs = hasher.digest_batch([candidate for _, candidate in valid])
            checked += len(valid)
            for (_, raw), digest in zip(valid, outputs):
                if digest == hasher.expected:
                    return {'found': True, 'password': raw.decode('utf-8', errors='backslashreplace'),
                            'password_hex': raw.hex(), 'elapsed_seconds': time.perf_counter() - started,
                            'candidates_checked': checked, 'total_candidates': total, 'backend': 'gpu',
                            'workers': len(valid), 'batch_size': batch_size, 'rejected': rejected,
                            'gpu_kernel_seconds': hasher.kernel_seconds, 'gpu_device': hasher.device_info()}
        return {'found': False, 'password': None, 'elapsed_seconds': time.perf_counter() - started,
                'candidates_checked': checked, 'total_candidates': total, 'backend': 'gpu',
                'workers': batch_size, 'batch_size': batch_size, 'rejected': rejected,
                'gpu_kernel_seconds': hasher.kernel_seconds, 'gpu_device': hasher.device_info()}
    finally:
        if file_handle is not None:
            file_handle.close()
