#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Создаёт каркас живой документации продукта `product_docs/` из `templates/product_docs/`.

    python init_product_docs.py            # создать, если папки ещё нет
    python init_product_docs.py --force    # дописать недостающие файлы в существующую папку

Существующие файлы никогда не перезаписываются: документация принадлежит проекту.
Строка-пример в INDEX.md и пустые шаблоны — это каркас; карточки БФ создаются аналитиком
по `product_docs/_templates/bf_card.md` (см. `product_docs/README.md`).
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "templates" / "product_docs"
TARGET = ROOT / "product_docs"


def copy_missing(source: Path, target: Path) -> tuple[list[Path], list[Path]]:
    created: list[Path] = []
    skipped: list[Path] = []
    for src in sorted(p for p in source.rglob("*") if p.is_file()):
        dst = target / src.relative_to(source)
        if dst.exists():
            skipped.append(dst)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        created.append(dst)
    return created, skipped


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="дописать недостающие файлы, если product_docs/ уже существует")
    args = ap.parse_args()

    if not SOURCE.is_dir():
        print(f"Не найден шаблон: {SOURCE}", file=sys.stderr)
        return 1
    if TARGET.exists() and not args.force:
        print(f"product_docs/ уже существует — ничего не изменено. "
              f"Чтобы дописать недостающие файлы: python init_product_docs.py --force")
        return 0

    created, skipped = copy_missing(SOURCE, TARGET)
    for p in created:
        print("создан:", p.relative_to(ROOT))
    if skipped:
        print(f"пропущено существующих файлов: {len(skipped)}")
    print("\nГотово. Дальше: product_docs/README.md, раздел «Как начать».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
