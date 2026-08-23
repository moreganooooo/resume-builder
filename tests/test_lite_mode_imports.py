"""
test_lite_mode_imports.py -- pins F20 (docs/review/master_audit_document.md).

`requirements-lite.txt` (Android/Termux, and desktops that only tailor and
sync rather than render) deliberately omits pandas and numpy. But
`orchestrator.py` imported both at module level and is reached by every
entry point, so a Lite install died at

    ModuleNotFoundError: No module named 'numpy'

on plain `resume` -- before any pipeline logic, and before any message that
could explain what was wrong. The audit filed this as "aspirational, not
shipped"; it became live the moment requirements-lite.txt shipped.

This test blocks pandas/numpy at import time and asserts every entry-point
module still imports. It is the only thing standing between a future
module-level `import pandas` and a completely broken Lite Mode -- the
failure is silent on a full desktop install, where both packages are always
present.
"""

import builtins
import importlib
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
for _p in (SCRIPTS_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Everything a Lite install can reach: the CLI, the menus, and the modules
# they pull in transitively. bullet_bank_menu is here because it is what
# actually reintroduced the crash after orchestrator.py was fixed.
LITE_SAFE_MODULES = [
    "jd_manager",
    "profile_paths",
    "picker",
    "orchestrator",
    "cli",
    "menu",
    "bootstrap_menu",
    "bootstrap_profile",
    "bootstrap_extractors",
    "bullet_bank_menu",
    "skills_menu",
    "doctor",
]

HEAVY = {"pandas", "numpy"}


class TestLiteModeImports(unittest.TestCase):
    def _import_without_heavy_deps(self, module_name):
        """Imports module_name with pandas/numpy made unavailable.

        Uses a fresh module cache so an already-imported module (the suite
        imports most of these) doesn't mask a module-level import.
        """
        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in HEAVY:
                raise ModuleNotFoundError(f"No module named '{name.split('.')[0]}'")
            return real_import(name, *args, **kwargs)

        saved = dict(sys.modules)
        for mod in list(sys.modules):
            if mod.split(".")[0] in HEAVY:
                del sys.modules[mod]
            elif mod in LITE_SAFE_MODULES:
                del sys.modules[mod]
        builtins.__import__ = guarded
        try:
            importlib.import_module(module_name)
        finally:
            builtins.__import__ = real_import
            sys.modules.clear()
            sys.modules.update(saved)

    def test_every_entry_point_imports_without_pandas_or_numpy(self):
        broken = []
        for module_name in LITE_SAFE_MODULES:
            try:
                self._import_without_heavy_deps(module_name)
            except ModuleNotFoundError as exc:
                broken.append(f"{module_name}: {exc}")
            except Exception as exc:  # NameError from an unquoted annotation
                broken.append(f"{module_name}: {type(exc).__name__}: {exc}")
        self.assertEqual(
            broken,
            [],
            "Lite Mode (requirements-lite.txt) omits pandas/numpy, so these "
            "modules must not import them at module level. Move the import "
            "inside the functions that use it and quote any pd.DataFrame "
            "annotation so it does not evaluate at def time:\n  " + "\n  ".join(broken),
        )


if __name__ == "__main__":
    unittest.main()
