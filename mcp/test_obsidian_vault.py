"""Тесты логики Obsidian vault (без COM)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from investigation_tracker import load_tracker, register_investigation
from obsidian_vault import (
    find_existing_vault_folder,
    resolve_context,
    resolve_vault_folder_name,
    russian_document_filename,
    save_requirements_note,
    save_session_note,
)


class TestObsidianVault(unittest.TestCase):
    def test_same_configuration_resolves_same_folder(self) -> None:
        session_a = {
            "configuration_name": "БИТУправлениеМедицинскимЦентром",
            "info_base_display_name": "БИТ:Управление медицинским центром (демо)",
        }
        session_b = {
            "configuration_name": "БИТУправлениеМедицинскимЦентром",
            "info_base_display_name": "БИТ Управление медицинским центром1",
        }
        folder_a = resolve_vault_folder_name(session_a)
        folder_b = resolve_vault_folder_name(session_b)
        self.assertEqual(folder_a, folder_b)
        self.assertEqual(folder_a, "БИТ Управление медицинским центром")

    def test_russian_filename_format(self) -> None:
        name = russian_document_filename(
            "ЛистТребований",
            "Заполнение титульного листа ЭМК",
            date="2026-06-10",
        )
        self.assertEqual(
            name,
            "2026-06-10_ЛистТребований_ЗаполнениеТитульногоЛистаЭМК.md",
        )

    def test_requirements_update_in_place_and_json_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "analyst"
            root.mkdir()
            session = {
                "configuration_name": "БИТУправлениеМедицинскимЦентром",
                "configuration_version": "2.0.49.97",
                "info_base_display_name": "БИТ:Управление медицинским центром (демо)",
            }

            first = save_requirements_note(
                root,
                title="Лист требований — Титульный лист ЭМК",
                body_markdown="## 4. Способ реализации\n\nДокумент.Прием",
                session=session,
                phase="draft",
                keywords=["ЭМК", "титульный лист"],
            )
            note_id = str(first["id"])
            rel_path = str(first["relative_path"])
            self.assertTrue(rel_path.endswith(".md"))
            self.assertTrue(str(first["json_relative_path"]).endswith(".json"))

            register_investigation(
                root,
                requirements_relative_path=rel_path,
                requirements_json_path=str(first["json_relative_path"]),
                requirements_id=note_id,
            )

            second = save_requirements_note(
                root,
                title="Лист требований — Титульный лист ЭМК",
                body_markdown="## 4. Способ реализации\n\nОбновлённый текст. Документ.Прием",
                session=session,
                phase="final",
                requirements_relative_path=rel_path,
                requirements_id=note_id,
            )
            self.assertEqual(second["relative_path"], rel_path)
            self.assertTrue(second.get("updated"))

            md_text = (root / "Obsidian" / rel_path.split("/", 1)[0] / rel_path.split("/", 1)[1]).read_text(
                encoding="utf-8"
            )
            self.assertIn("configurationVersion: 2.0.49.97", md_text)
            self.assertIn("[[Документ.Прием]]", md_text)
            self.assertIn("## Связи", md_text)
            self.assertEqual(md_text.count("id: "), 1)

            json_path = root / "Obsidian" / str(second["json_relative_path"])
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["type"], "requirements")
            self.assertEqual(payload["id"], note_id)
            self.assertEqual(payload["phase"], "final")

            tracker = load_tracker(root)
            self.assertEqual(tracker.get("requirementsRelativePath"), rel_path)

    def test_find_existing_legacy_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "Obsidian"
            legacy = vault / "БИТ-Управление медицинским центром (демо)" / "Requirements"
            legacy.mkdir(parents=True)
            session = {
                "configuration_name": "БИТУправлениеМедицинскимЦентром",
                "info_base_display_name": "БИТ Управление медицинским центром1",
            }
            found = find_existing_vault_folder(vault, session=session)
            self.assertEqual(found, "БИТ-Управление медицинским центром (демо)")

    def test_session_note_updates_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "analyst"
            root.mkdir()
            session = {"configuration_name": "УправлениеТорговлей", "configuration_version": "11.5.1"}

            first = save_session_note(
                root,
                summary="Расследование закрытия месяца",
                session=session,
                mode="live",
            )
            second = save_session_note(
                root,
                summary="Расследование закрытия месяца — уточнение",
                session=session,
                mode="live",
                session_relative_path=str(first["relative_path"]),
            )
            self.assertEqual(first["relative_path"], second["relative_path"])
            self.assertTrue(second.get("updated"))

    def test_resolve_context_contains_display_name(self) -> None:
        context = resolve_context(
            session={
                "configuration_name": "БИТУправлениеМедицинскимЦентром",
                "configuration_version": "2.0.49.97",
                "info_base_display_name": "БИТ:Управление медицинским центром (демо)",
            }
        )
        self.assertEqual(context["vault_folder"], "БИТ Управление медицинским центром")
        self.assertEqual(context["configuration_version"], "2.0.49.97")


if __name__ == "__main__":
    unittest.main()
