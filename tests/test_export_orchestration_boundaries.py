"""Export orchestration boundary tests with synthetic data only."""
from __future__ import annotations

import ast
import inspect
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from garmin_auto_coach import core, export_service
from test_regression_golden import TODAY, GOALS, FrozenDateTime, create_synthetic_input


class ExportOrchestrationTests(unittest.TestCase):
    def test_legacy_api_signature_unchanged(self):
        self.assertEqual(
            str(inspect.signature(core.generate_exports)),
            "(private_dir: 'Path', export_dir: 'Path', goals: 'str' = '', today: 'date | None' = None) -> 'dict'",
        )

    def test_compatibility_facade_delegates_injected_dependencies(self):
        with patch.object(export_service, "generate_exports", return_value={"synthetic": True}) as mock:
            result = core.generate_exports(Path("fake-private"), Path("fake-output"), "goal", TODAY)
        self.assertEqual(result, {"synthetic": True})
        deps = mock.call_args.kwargs["deps"]
        self.assertIs(deps.week_summary, core.week_summary)
        self.assertIs(deps.coach_context, core.coach_context)
        self.assertIs(deps.local_today, core.local_today)
        self.assertIs(deps.activity_columns, core.ACTIVITY_COLUMNS)
        self.assertIs(deps.wellness_columns, core.WELLNESS_COLUMNS)
        self.assertEqual(mock.call_args.kwargs["today"], TODAY)

    def test_default_clock_and_today_callbacks_preserved(self):
        with tempfile.TemporaryDirectory(prefix="garmin-export-clock-") as tmp:
            root = Path(tmp)
            create_synthetic_input(root / "private")
            with patch.object(core, "datetime", FrozenDateTime), patch.object(core, "local_today", return_value=TODAY):
                output = core.generate_exports(root / "private", root / "export", GOALS)
            self.assertTrue(output["generated_at"].startswith("2026-10-29T12:00:00"))
            self.assertTrue((root / "export" / "training_analysis.md").is_file())
            self.assertEqual(output["activities"], 11)

    def test_service_has_no_core_or_garmin_api_imports(self):
        source = Path(export_service.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
        self.assertNotIn("core", imports)
        self.assertNotIn("garmin_auto_coach.core", imports)
        self.assertFalse(any("garmin_personal_api" in name for name in imports))

    def test_service_explicit_dependencies_and_local_files(self):
        with tempfile.TemporaryDirectory(prefix="garmin-export-boundary-") as tmp:
            root = Path(tmp)
            create_synthetic_input(root / "private")
            fixed = datetime(2026, 10, 29, 12)
            deps = export_service.ExportDependencies(
                activity_columns=core.ACTIVITY_COLUMNS,
                wellness_columns=core.WELLNESS_COLUMNS,
                local_today=lambda: TODAY,
                now=lambda: fixed,
                week_summary=core.week_summary,
                coach_context=core.coach_context,
            )
            result = export_service.generate_exports(root / "private", root / "exports", GOALS, TODAY, deps=deps)
            self.assertEqual(result["activities"], 11)
            self.assertEqual(result["generated_at"], fixed.isoformat())
            self.assertTrue((root / "exports" / "training_metrics.json").exists())


if __name__ == "__main__":
    unittest.main()
