"""The solver. Pure arithmetic, so it is cheap to pin down exactly."""

from __future__ import annotations

import unittest

from paddocks.layout import Metrics, size_for, solve


class SizeFor(unittest.TestCase):
    def setUp(self):
        self.m = Metrics()

    def test_a_full_row_is_max_columns_wide(self):
        width, height, rows = size_for(4, self.m)
        self.assertEqual((width, height, rows), (4 * 140 + 32, 44 + 140 + 28, 1))

    def test_six_icons_balance_three_and_three(self):
        # Quicklaunch spreads icons evenly over the rows it is given, so six in
        # two rows render 3+3. Sizing to four columns would leave it room to
        # scale the icons up and every group a different size.
        width, _, rows = size_for(6, self.m)
        self.assertEqual(rows, 2)
        self.assertEqual(width, 3 * 140 + 32)

    def test_seven_icons_still_need_four_columns(self):
        width, _, rows = size_for(7, self.m)
        self.assertEqual((rows, width), (2, 4 * 140 + 32))

    def test_a_single_icon_is_held_up_by_the_minimum_width(self):
        width, height, rows = size_for(1, self.m)
        self.assertEqual((width, height, rows), (180, 212, 1))

    def test_an_empty_group_still_has_a_box(self):
        width, height, rows = size_for(0, self.m)
        self.assertGreaterEqual(width, self.m.min_width)
        self.assertGreaterEqual(height, self.m.min_height)
        self.assertEqual(rows, 1)


class Solve(unittest.TestCase):
    def setUp(self):
        self.m = Metrics()
        self.screen = (1920, 1080)

    def test_a_row_wraps_when_it_runs_out_of_width(self):
        boxes = solve([(f"G{i}", 4) for i in range(6)], self.screen, self.m, "row")
        self.assertGreater(len({b.y for b in boxes}), 1)
        self.assertTrue(all(b.x + b.w <= self.screen[0] for b in boxes))

    def test_grid_puts_three_in_a_row(self):
        boxes = solve([(f"G{i}", 1) for i in range(4)], self.screen, self.m, "grid")
        self.assertEqual(boxes[0].y, boxes[2].y)
        self.assertGreater(boxes[3].y, boxes[0].y)

    def test_column_puts_one_in_a_row(self):
        boxes = solve([("A", 1), ("B", 1)], self.screen, self.m, "column")
        self.assertGreater(boxes[1].y, boxes[0].y)

    def test_centre_alignment_centres_the_row(self):
        boxes = solve([("A", 1)], self.screen, self.m, "row")
        self.assertEqual(boxes[0].x, (1920 - boxes[0].w) // 2)

    def test_left_alignment_starts_at_the_margin(self):
        boxes = solve([("A", 1)], self.screen, Metrics(align="left"), "row")
        self.assertEqual(boxes[0].x, self.m.margin)

    def test_mixed_heights_are_centred_within_their_row(self):
        boxes = solve([("tall", 8), ("short", 2)], self.screen, self.m, "row")
        tall, short = boxes
        self.assertGreater(short.y, tall.y)
        self.assertEqual(tall.y + tall.h // 2, short.y + short.h // 2)

    def test_a_layout_taller_than_the_screen_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            solve([(f"G{i}", 4) for i in range(6)], (1920, 300), self.m, "row")
        self.assertIn("taller than the usable screen", str(caught.exception))

    def test_unknown_arrangement_is_refused(self):
        with self.assertRaises(ValueError):
            solve([("A", 1)], self.screen, self.m, "diagonal")


if __name__ == "__main__":
    unittest.main()
