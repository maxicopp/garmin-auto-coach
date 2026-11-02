"""Contract checks for the storage extraction; synthetic files only."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from garmin_auto_coach import core, storage


class StorageBoundaryTests(unittest.TestCase):
    def test_legacy_core_exports_still_resolve_to_storage(self):
        for name in ("atomic_json", "atomic_text", "json_file", "digest", "load_rows", "csv_output"):
            with self.subTest(name=name):
                self.assertIs(getattr(core, name), getattr(storage, name))

    def test_atomic_json_and_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested" / "sample.json"
            record = {"synthetic": [1, 2, 3], "message": "testing"}
            storage.atomic_json(path, record)
            self.assertEqual(storage.json_file(path), record)
            self.assertEqual(path.read_bytes(),
                             (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
            expected_digest = hashlib.sha256(json.dumps(
                record, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
            self.assertEqual(storage.digest(record), expected_digest)

    def test_csv_contract_and_duplicate_write(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reports" / "test.csv"
            columns = ["activity_id", "distance_km", "missing"]
            rows = [{"activity_id": 1234, "distance_km": 10.5, "extra": "ignored"}]
            storage.csv_output(path, columns, rows)
            before = path.read_bytes()
            self.assertEqual(before, b"activity_id,distance_km,missing\r\n1234,10.5,\r\n")
            storage.csv_output(path, columns, rows)
            self.assertEqual(path.read_bytes(), before)
            with path.open(newline="") as fh:
                self.assertEqual(list(csv.DictReader(fh))[0]["activity_id"], "1234")

    def test_storage_has_no_package_imports(self):
        # Infrastructure must not depend on core, analytics, sync, or CLI.
        import ast
        tree = ast.parse(Path(storage.__file__).read_text(encoding="utf-8"))
        self.assertFalse([node for node in ast.walk(tree)
                          if isinstance(node, ast.ImportFrom) and node.level > 0])


if __name__ == "__main__":
    unittest.main()
