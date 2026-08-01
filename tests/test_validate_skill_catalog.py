from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_skill_catalog",
    ROOT / "scripts/validate_skill_catalog.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SkillCatalogValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = MODULE.load()

    def test_current_catalog_is_valid(self) -> None:
        self.assertEqual(MODULE.validate(self.catalog), [])

    def test_development_complete_is_exact_and_not_category_derived(self) -> None:
        self.assertIsNone(self.catalog["default_preset"])
        self.assertEqual(
            self.catalog["presets"]["development-complete"]["members"],
            MODULE.DEVELOPMENT_COMPLETE,
        )
        self.assertEqual(len(MODULE.DEVELOPMENT_COMPLETE), 11)

    def test_methods_and_lenses_are_distinct_discovery_categories(self) -> None:
        skills = self.catalog["skills"]
        methods = {
            skill_id
            for skill_id, entry in skills.items()
            if "software-design-method" in entry["categories"]
        }
        lenses = {
            skill_id
            for skill_id, entry in skills.items()
            if "software-architecture-lens" in entry["categories"]
        }

        self.assertEqual(methods, set(MODULE.SOFTWARE_DESIGN_METHODS))
        self.assertEqual(lenses, set(MODULE.SOFTWARE_ARCHITECTURE_LENSES))
        self.assertFalse(methods & lenses)
        self.assertEqual(
            self.catalog["presets"]["development-complete"]["members"],
            [*MODULE.SOFTWARE_DESIGN_METHODS, *MODULE.SOFTWARE_ARCHITECTURE_LENSES],
        )

    def test_wildcard_or_category_member_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["presets"]["development-complete"]["members"] = ["book-*"]
        self.assertTrue(
            any("wildcard or category expansion is forbidden" in error for error in MODULE.validate(catalog))
        )

    def test_default_preset_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["default_preset"] = "development-complete"
        self.assertIn("default_preset must be null", MODULE.validate(catalog))

    def test_unclassified_source_skill_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        del catalog["skills"]["prototype"]
        self.assertTrue(any("catalog differs from source" in error for error in MODULE.validate(catalog)))


if __name__ == "__main__":
    unittest.main()
