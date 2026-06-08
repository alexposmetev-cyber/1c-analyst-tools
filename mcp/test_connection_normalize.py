"""Локальные тесты нормализации параметров connect (без COM)."""

from __future__ import annotations

import unittest

from connection_session import merge_connect_inputs, normalize_info_base_path, parse_connect_string


class TestConnectionNormalize(unittest.TestCase):
    def test_parse_file_connect(self) -> None:
        connect = 'File="C:\\Users\\aaposmetev\\Documents\\1C\\DemoTrd";'
        parsed = parse_connect_string(connect)
        self.assertEqual(parsed["info_base_path"], r"C:\Users\aaposmetev\Documents\1C\DemoTrd")

    def test_normalize_strips_file_prefix(self) -> None:
        raw = 'File="C:\\ib\\DemoTrd";'
        self.assertEqual(normalize_info_base_path(raw), r"C:\ib\DemoTrd")

    def test_merge_plain_path(self) -> None:
        merged = merge_connect_inputs(
            user="Администратор",
            info_base_path=r"C:\Users\aaposmetev\Documents\1C\DemoTrd",
        )
        self.assertEqual(merged["info_base_path"], r"C:\Users\aaposmetev\Documents\1C\DemoTrd")
        self.assertEqual(merged["user"], "Администратор")

    def test_merge_connection_string(self) -> None:
        merged = merge_connect_inputs(
            connection_string='File="C:\\ib\\base";Usr="User1";Pwd="secret";',
        )
        self.assertEqual(merged["info_base_path"], r"C:\ib\base")
        self.assertEqual(merged["user"], "User1")
        self.assertEqual(merged["password"], "secret")


if __name__ == "__main__":
    unittest.main()
