# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Patching the applet background, in both of its variants.

The variant is the part that is easy to get wrong, and was wrong here until
2026-08-21. A theme ships `widgets/background` and, usually,
`translucent/widgets/background`; KSvg resolves the second one ahead of the
first whenever compositing and blur are active. Shadowing only the plain asset
therefore looks like it works -- the opacity does change -- while quietly
dropping the `blurred-mask-*` elements the translucent variant carries.
"""

from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paddocks import translucency

FRAME = """<svg>
  <g id="center"><path style="fill:currentColor"/></g>
  <g id="top"/><g id="bottom"/><g id="left"/><g id="right"/>
  <g id="topleft"/><g id="topright"/><g id="bottomleft"/><g id="bottomright"/>
  <g id="shadow-top"/>
  <g id="hint-stretch-borders"/>
</svg>"""

VARIANT = FRAME.replace("<g id=\"shadow-top\"/>",
                        "<g id=\"shadow-top\"/><g id=\"blurred-mask-center\"/>")


class Patching(unittest.TestCase):
    def test_every_frame_element_is_given_the_opacity(self):
        patched, count = translucency._patch_svg(FRAME, 0.4)
        self.assertEqual(count, 9)
        self.assertEqual(patched.count('opacity="0.4"'), 9)

    def test_shadows_are_left_alone(self):
        """Translucent shadows stop a frame reading against a busy wallpaper."""
        patched, _ = translucency._patch_svg(FRAME, 0.4)
        self.assertIn('<g id="shadow-top"/>', patched)

    def test_blur_masks_are_left_alone(self):
        """The masks are the blur region, not artwork -- opacity would shrink it."""
        patched, _ = translucency._patch_svg(VARIANT, 0.4)
        self.assertIn('<g id="blurred-mask-center"/>', patched)

    def test_an_element_that_already_says_opacity_is_not_doubled_up(self):
        already = FRAME.replace('<g id="top"/>', '<g id="top" opacity="0.9"/>')
        patched, count = translucency._patch_svg(already, 0.4)
        self.assertEqual(count, 8)
        self.assertIn('opacity="0.9"', patched)


class BothVariants(unittest.TestCase):
    """apply() against a fake theme tree, with no plasmashell in sight."""

    def _run(self, *, ship_variant: bool):
        tmp = Path(tempfile.mkdtemp())
        system, user = tmp / "system", tmp / "user"
        theme = system / "mytheme"
        (theme / "widgets").mkdir(parents=True)
        (theme / "widgets" / "background.svg").write_text(FRAME)
        if ship_variant:
            (theme / "translucent" / "widgets").mkdir(parents=True)
            (theme / "translucent" / "widgets" / "background.svg").write_text(VARIANT)

        with mock.patch.object(translucency, "SYSTEM_THEME_DIRS", [system]), \
             mock.patch.object(translucency, "USER_THEMES", user), \
             mock.patch.object(translucency, "active_themes",
                               return_value=["mytheme"]):
            translucency.apply(0.4, restart=False)
        return user / "mytheme"

    def read(self, path: Path) -> str:
        return gzip.open(path).read().decode()

    def test_the_plain_asset_is_patched(self):
        out = self._run(ship_variant=True)
        self.assertEqual(
            self.read(out / "widgets" / "background.svgz").count('opacity="0.4"'), 9)

    def test_the_translucent_variant_is_patched_too(self):
        out = self._run(ship_variant=True)
        variant = out / "translucent" / "widgets" / "background.svgz"
        self.assertTrue(variant.exists(),
                        "the blur-aware variant was not shadowed, so blur is lost")
        self.assertEqual(self.read(variant).count('opacity="0.4"'), 9)

    def test_the_variant_keeps_its_blur_masks(self):
        out = self._run(ship_variant=True)
        variant = self.read(out / "translucent" / "widgets" / "background.svgz")
        self.assertIn('id="blurred-mask-center"', variant)

    def test_a_theme_without_a_variant_still_works(self):
        """Not every theme ships one; its absence is not an error."""
        out = self._run(ship_variant=False)
        self.assertTrue((out / "widgets" / "background.svgz").exists())
        self.assertFalse((out / "translucent").exists())
