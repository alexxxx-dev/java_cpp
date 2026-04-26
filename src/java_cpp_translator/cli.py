from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .translator import JavaToCppTranslator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Транслятор поддерживаемого подмножества Java в C++17")
    parser.add_argument("inputs", nargs="+", help="исходные .java файлы")
    parser.add_argument("-o", "--output-dir", default="out", help="каталог для .h/.cpp файлов")
    args = parser.parse_args(argv)

    translator = JavaToCppTranslator()
    summary = translator.translate_many(args.inputs, args.output_dir)
    for diagnostic in translator.diagnostics.items:
        print(diagnostic.format_ru(), file=sys.stderr)
    print(
        f"Обработано файлов: {summary['processed_files']}, файлов с ошибками: {summary['files_with_errors']}, "
        f"ошибок: {summary['errors']}, предупреждений: {summary['warnings']}"
    )
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
