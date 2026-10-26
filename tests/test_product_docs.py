"""
tests/test_product_docs.py — слой живой документации `product_docs/` (KON-129).

Covers:
  - init_product_docs.copy_missing: создаёт каркас и никогда не перезаписывает существующие файлы;
  - шаблон product_docs/ в свежем проекте проходит проверку без ошибок;
  - check_product_docs.py: ловит ID, которого нет в графе; устаревшую версию в карточке;
    битую ссылку; БФ без строки INDEX; planned без «Планируемого изменения»;
    --fix обновляет таблицу требований из графа.
Скрипты запускаются как подпроцесс на временной копии проекта: так проверяется ровно то, что получит пользователь.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = PROJECT_ROOT / "templates" / "product_docs"
PID = "demo_proj"


def _load_init():
    spec = importlib.util.spec_from_file_location("init_product_docs", PROJECT_ROOT / "init_product_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CARD = """# BF-01 — Тестовая функция

| Атрибут | Значение |
|---|---|
| Версия БФ | 1.0 |
| Статус | {status} |
| Релиз | MVP |

{planned}## Требования (слой 1)

| ID | Название | Версия / статус (граф 5.1) | Спецификация |
|---|---|---|---|
| {req} | | | |

## Техническое решение (C3): компоненты
* comp_a

## История изменений
| Версия БФ | Дата | CR | Что изменилось |
|---|---|---|---|
"""

INDEX = """# INDEX

| БФ | Название | Требования | Компоненты | UI | Релиз | Карточка |
|---|---|---|---|---|---|---|
{row}
Сквозные: NFR-001
"""


class ProductDocsCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEMPLATE, self.tmp / "product_docs")
        data = self.tmp / "output" / "data" / PID
        (data / "specs").mkdir(parents=True)
        self.graph_path = data / f"{PID}_traceability_repo.json"
        self._graph = {
            "requirements": [
                {"id": "FR-001", "type": "functional", "title": "Первое требование", "version": "1.0", "status": "approved"},
                {"id": "NFR-001", "type": "non_functional", "title": "Сквозное", "version": "1.0", "status": "approved"},
            ],
            "links": [],
        }
        self.write_graph()
        (data / "specs" / "fr_001_pervoe.md").write_text("# FR-001", encoding="utf-8")
        comp = self.tmp / "product_docs" / "02_system_components" / "comp_a"
        comp.mkdir(parents=True)
        (comp / "README.md").write_text("# comp_a", encoding="utf-8")
        self.set_card(status="implemented", req="FR-001")
        self.set_index(row="| BF-01 | Тест | FR-001 | comp_a | — | MVP | [BF-01_test](01_business_functions/BF-01_test/README.md) |")
        self.run_check("--fix")  # заполняет название/версию/ссылку в таблице карточки

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- вспомогательное --
    def write_graph(self):
        self.graph_path.write_text(json.dumps(self._graph, ensure_ascii=False), encoding="utf-8")

    def set_card(self, status, req, planned=""):
        d = self.tmp / "product_docs" / "01_business_functions" / "BF-01_test"
        d.mkdir(parents=True, exist_ok=True)
        (d / "README.md").write_text(CARD.format(status=status, req=req, planned=planned), encoding="utf-8")

    def set_index(self, row):
        (self.tmp / "product_docs" / "INDEX.md").write_text(INDEX.format(row=row), encoding="utf-8")

    def run_check(self, *args):
        return subprocess.run(
            [sys.executable, "-I", str(self.tmp / "product_docs" / "check_product_docs.py"), *args],
            capture_output=True, text=True, encoding="utf-8", cwd=self.tmp,
        )

    # -- тесты --
    def test_clean_project_passes(self):
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ошибок 0", r.stdout)

    def test_unknown_requirement_id_is_error(self):
        self.set_card(status="implemented", req="FR-099")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FR-099 нет в графе", r.stdout)

    def test_stale_version_detected_and_fixed(self):
        self._graph["requirements"][0]["version"] = "2.0"
        self.write_graph()
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FR-001", r.stdout)
        fixed = self.run_check("--fix")
        self.assertEqual(fixed.returncode, 0, fixed.stdout)
        card = (self.tmp / "product_docs" / "01_business_functions" / "BF-01_test" / "README.md").read_text(encoding="utf-8")
        self.assertIn("2.0 / approved", card)
        self.assertEqual(self.run_check().returncode, 0)

    def test_broken_link_is_error(self):
        card = self.tmp / "product_docs" / "01_business_functions" / "BF-01_test" / "README.md"
        card.write_text(card.read_text(encoding="utf-8") + "\n[нет](../../нет_такого.md)\n", encoding="utf-8")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("ссылка не ведёт к файлу", r.stdout)

    def test_card_without_index_row_is_error(self):
        self.set_index(row="")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("нет строки в INDEX", r.stdout)

    def test_planned_without_section_is_error(self):
        self.set_card(status="planned", req="FR-001")
        r = self.run_check("--fix")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Планируемое изменение", r.stdout)

    def test_planned_with_section_passes(self):
        self.set_card(status="planned", req="FR-001",
                      planned="## Планируемое изменение\nДобавляется FR-001: описание изменения, затрагивает comp_a, открытых вопросов нет.\n\n")
        r = self.run_check("--fix")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_unknown_status_is_error(self):
        self.set_card(status="готово", req="FR-001")
        self.assertEqual(self.run_check().returncode, 1)

    def test_uncovered_requirement_is_warning_only(self):
        self._graph["requirements"].append(
            {"id": "FR-002", "type": "functional", "title": "Без БФ", "version": "1.0", "status": "approved"})
        self.write_graph()
        r = self.run_check()
        self.assertEqual(r.returncode, 0)
        self.assertIn("FR-002", r.stdout)


class InitProductDocsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.init = _load_init()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_skeleton(self):
        created, skipped = self.init.copy_missing(TEMPLATE, self.tmp / "product_docs")
        names = {p.relative_to(self.tmp / "product_docs").as_posix() for p in created}
        for expected in ("README.md", "INDEX.md", "_templates/bf_card.md", "_templates/component_page.md",
                         "check_product_docs.py", "render_diagrams.sh",
                         "01_business_functions/.gitkeep", "02_system_components/.gitkeep"):
            self.assertIn(expected, names)
        self.assertEqual(skipped, [])

    def test_never_overwrites_existing_files(self):
        target = self.tmp / "product_docs"
        target.mkdir()
        (target / "INDEX.md").write_text("моё содержимое", encoding="utf-8")
        created, skipped = self.init.copy_missing(TEMPLATE, target)
        self.assertEqual((target / "INDEX.md").read_text(encoding="utf-8"), "моё содержимое")
        self.assertIn(target / "INDEX.md", skipped)
        self.assertNotIn(target / "INDEX.md", created)

    def test_script_refuses_when_folder_exists(self):
        shutil.copy2(PROJECT_ROOT / "init_product_docs.py", self.tmp / "init_product_docs.py")
        shutil.copytree(TEMPLATE, self.tmp / "templates" / "product_docs")
        (self.tmp / "product_docs").mkdir()
        r = subprocess.run([sys.executable, "-I", str(self.tmp / "init_product_docs.py")],
                           capture_output=True, text=True, encoding="utf-8", cwd=self.tmp)
        self.assertEqual(r.returncode, 0)
        self.assertIn("уже существует", r.stdout)
        self.assertFalse((self.tmp / "product_docs" / "README.md").exists())

    def test_fresh_template_passes_check(self):
        shutil.copy2(PROJECT_ROOT / "init_product_docs.py", self.tmp / "init_product_docs.py")
        shutil.copytree(TEMPLATE, self.tmp / "templates" / "product_docs")
        data = self.tmp / "output" / "data" / PID
        data.mkdir(parents=True)
        (data / f"{PID}_traceability_repo.json").write_text(json.dumps({"requirements": [], "links": []}), encoding="utf-8")
        subprocess.run([sys.executable, "-I", str(self.tmp / "init_product_docs.py")],
                       capture_output=True, text=True, encoding="utf-8", cwd=self.tmp, check=True)
        r = subprocess.run([sys.executable, "-I", str(self.tmp / "product_docs" / "check_product_docs.py")],
                           capture_output=True, text=True, encoding="utf-8", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
