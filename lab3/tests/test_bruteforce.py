import hashlib
import json
from pathlib import Path
import unittest

from lab3.src.candidates import iter_candidates
from lab3.src.cpu import crack
from lab3.src.hashes import HashTarget, TargetError
from lab3.src.models import CrackConfig


class BruteForceTests(unittest.TestCase):
    def test_generation_order_and_exact_count(self):
        config = CrackConfig('01', 1, 2)
        self.assertEqual(list(iter_candidates(config)), [b'0', b'1', b'00', b'01', b'10', b'11'])
        self.assertEqual(config.validate(), 6)

    def test_all_algorithms_one_and_two_workers(self):
        import bcrypt
        from argon2 import PasswordHasher
        encoded = [hashlib.md5(b'ba', usedforsecurity=False).hexdigest(), hashlib.sha1(b'ba').hexdigest(),
                   bcrypt.hashpw(b'ba', bcrypt.gensalt(4)).decode(),
                   PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash('ba')]
        for workers in (1, 2):
            for value in encoded:
                with self.subTest(workers=workers, hash=value):
                    result = crack(HashTarget.parse(value), CrackConfig('ab', 1, 2, workers))
                    self.assertEqual(result.password, 'ba')
                    self.assertEqual(result.workers, workers)
                    self.assertEqual(result.backend, 'cpu')

    def test_exhaustion_and_completed_checks(self):
        result = crack(HashTarget.parse(hashlib.md5(b'outside', usedforsecurity=False).hexdigest()), CrackConfig('ab', 1, 2, 2))
        self.assertFalse(result.found)
        self.assertEqual(result.candidates_checked, 6)
        self.assertEqual(result.total_candidates, 6)

    def test_invalid_config_and_hash(self):
        for config in (CrackConfig('aa', 1, 2), CrackConfig('', 1, 2), CrackConfig('ab', 2, 1),
                       CrackConfig('0123456789', 1, 8), CrackConfig('ab', 1, 1, 0), CrackConfig('a\x1b', 1, 1)):
            with self.subTest(config=config), self.assertRaises(ValueError):
                config.validate()
        for value in ('invalid', '$2b$99$'+'a'*53, '$argon2id$v=19$m=8,t=1,p=8$c2FsdHNhbHQ$YWJjZA'):
            with self.subTest(value=value), self.assertRaises(TargetError):
                HashTarget.parse(value)
        with self.assertRaises(ValueError):
            crack(HashTarget('sha1', '0'*32), CrackConfig('ab', 1, 1))

    def test_all_assignment_hashes_and_known_passwords(self):
        data = json.loads((Path(__file__).parents[1]/'examples/assignment-hashes.json').read_text(encoding='utf-8'))
        for algorithm in ('md5', 'sha1', 'bcrypt', 'argon2id'):
            for level, encoded in data[algorithm].items():
                target = HashTarget.parse(encoded)
                self.assertEqual(target.algorithm, algorithm)
                if level in ('easy', 'medium'):
                    self.assertTrue(target.matches('123456' if level == 'easy' else 'apple'))
