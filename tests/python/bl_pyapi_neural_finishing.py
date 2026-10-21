# SPDX-FileCopyrightText: 2026 Jason Lok
# SPDX-License-Identifier: GPL-2.0-or-later
"""Non-rendering checks for the WIP native operators. No optional worker needed."""
import os
import unittest
from unittest import mock

import bpy
from bl_operators import neural_finishing


class NeuralFinishingTest(unittest.TestCase):
    def test_registered_default_off(self):
        settings = bpy.context.window_manager.neural_finishing
        self.assertFalse(settings.enabled)
        self.assertFalse(settings.running)
        self.assertIsNone(neural_finishing._process)
        self.assertEqual(settings.mode, "STILL")

    @unittest.skipUnless(os.name == "nt", "Current backend is Windows-only")
    def test_other_render_blocks_before_snapshot(self):
        settings = bpy.context.window_manager.neural_finishing
        settings.enabled = True
        try:
            with mock.patch.object(neural_finishing, "_background_render_exists", return_value=True):
                with self.assertRaisesRegex(ValueError, "Another Blender render"):
                    neural_finishing._preflight(bpy.context, settings)
        finally:
            settings.enabled = False

    def test_disabled_feature_never_launches(self):
        settings = bpy.context.window_manager.neural_finishing
        settings.enabled = False
        with mock.patch.object(neural_finishing, "_background_render_exists", return_value=False):
            with mock.patch.object(neural_finishing.subprocess, "Popen", side_effect=AssertionError("No process allowed")):
                with self.assertRaises((ValueError, RuntimeError)):
                    neural_finishing._preflight(bpy.context, settings)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
