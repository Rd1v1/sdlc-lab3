import hashlib
import importlib.util
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from lab3.src.models import CrackConfig
from lab3.src.hashes import HashTarget, TargetError
from lab3.src.candidates import candidate_at, iter_candidates
from lab3.src.cpu import crack


class BruteForceTests(unittest.TestCase):
    def test_known_md5_and_sha1_vectors(self):
        self.assertEqual(hashlib.md5(b"abc", usedforsecurity=False).hexdigest(), "900150983cd24fb0d6963f7d28e17f72")
        self.assertEqual(hashlib.sha1(b"abc", usedforsecurity=False).hexdigest(), "a9993e364706816aba3e25717850c26c9cd0d89d")
        self.assertTrue(HashTarget.parse("900150983CD24FB0D6963F7D28E17F72").matches("abc"))
        self.assertTrue(HashTarget.parse("a9993e364706816aba3e25717850c26c9cd0d89d").matches("abc"))

    def test_candidate_generation_has_expected_order(self):
        config = CrackConfig("01", 1, 2, candidate_limit=6)
        self.assertEqual(list(iter_candidates(config)), ["0", "1", "00", "01", "10", "11"])
        self.assertEqual(candidate_at(5, "012", 2), "12")

    def test_bounded_success_and_not_found(self):
        target = HashTarget.parse(hashlib.md5(b"12", usedforsecurity=False).hexdigest())
        result = crack(target, CrackConfig("012", 1, 2, candidate_limit=12))
        self.assertTrue(result.found)
        self.assertEqual(result.password, "12")
        self.assertEqual(result.candidates_checked, 9)

        absent = HashTarget.parse(hashlib.sha1(b"outside-range", usedforsecurity=False).hexdigest())
        result = crack(absent, CrackConfig("01", 1, 2, candidate_limit=6))
        self.assertFalse(result.found)
        self.assertIsNone(result.password)
        self.assertEqual(result.candidates_checked, result.total_candidates)

    def test_parallel_mode_finds_target(self):
        target = HashTarget.parse(hashlib.sha1(b"321", usedforsecurity=False).hexdigest())
        result = crack(target, CrackConfig("0123456789", 3, 3, candidate_limit=1000, workers=2))
        self.assertTrue(result.found)
        self.assertEqual(result.password, "321")
        self.assertGreaterEqual(result.candidates_checked, 1)

    def test_parallel_counter_matches_actual_verifier_calls(self):
        target = HashTarget.parse(hashlib.md5(b"99", usedforsecurity=False).hexdigest())
        checked_candidates = []
        checked_lock = threading.Lock()
        original_matches = HashTarget.matches

        def counted_matches(instance, candidate):
            with checked_lock:
                checked_candidates.append(candidate)
            time.sleep(0.001)
            return original_matches(instance, candidate)

        with patch.object(HashTarget, "matches", counted_matches):
            result = crack(target, CrackConfig("0123456789", 2, 2, candidate_limit=100, workers=2))
        self.assertTrue(result.found)
        self.assertEqual(result.candidates_checked, len(checked_candidates))

    def test_rejects_invalid_or_excessive_search(self):
        for encoded in ("", "xyz", "$2b$99$" + "a" * 53, "$argon2id$v=19$m=999999999,t=1,p=1$salt$hash"):
            with self.subTest(encoded=encoded), self.assertRaises(TargetError):
                HashTarget.parse(encoded)
        with self.assertRaises(ValueError):
            crack(HashTarget.parse("900150983cd24fb0d6963f7d28e17f72"), CrackConfig("0123456789", 1, 8, candidate_limit=10))
        with self.assertRaises(ValueError):
            CrackConfig("001", 1, 2).validate()

    @unittest.skipUnless(importlib.util.find_spec("bcrypt"), "bcrypt dependency is installed in .venv")
    def test_bcrypt_vector_verification_and_search(self):
        import bcrypt

        encoded = bcrypt.hashpw(b"ab", bcrypt.gensalt(rounds=4)).decode("ascii")
        target = HashTarget.parse(encoded)
        result = crack(target, CrackConfig("ab", 1, 2, candidate_limit=6))
        self.assertTrue(result.found)
        self.assertEqual(result.password, "ab")

    @unittest.skipUnless(importlib.util.find_spec("argon2"), "argon2-cffi dependency is installed in .venv")
    def test_argon2_vector_verification_and_search(self):
        from argon2 import PasswordHasher

        encoded = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("ba")
        target = HashTarget.parse(encoded)
        result = crack(target, CrackConfig("ab", 1, 2, candidate_limit=6))
        self.assertTrue(result.found)
        self.assertEqual(result.password, "ba")

    def test_assignment_easy_and_medium_hashes(self):
        path = Path(__file__).parents[1] / "examples" / "assignment-hashes.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for algorithm in ("md5", "sha1", "bcrypt", "argon2id"):
            with self.subTest(algorithm=algorithm):
                self.assertTrue(HashTarget.parse(data[algorithm]["easy"]).matches("123456"))
                self.assertTrue(HashTarget.parse(data[algorithm]["medium"]).matches("apple"))

    def test_all_assignment_hashes_are_recognized(self):
        path = Path(__file__).parents[1] / "examples" / "assignment-hashes.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        expected = {"md5": "md5", "sha1": "sha1", "bcrypt": "bcrypt", "argon2id": "argon2id"}
        for algorithm, labels in data.items():
            if algorithm not in expected:
                continue
            for label, encoded in labels.items():
                with self.subTest(algorithm=algorithm, label=label):
                    self.assertEqual(HashTarget.parse(encoded).algorithm, expected[algorithm])


if __name__ == "__main__":
    unittest.main()
