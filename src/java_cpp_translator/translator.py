from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .diagnostics import DiagnosticBag, Stage, TranslationError, ru_message
from .generator import CppGenerator, GeneratedFile
from .lexer import Lexer
from .parser import Parser
from .semantic import SemanticAnalyzer


class JavaToCppTranslator:
    def __init__(self) -> None:
        self.diagnostics = DiagnosticBag()

    def translate_text(self, text: str, filename: str, base_name: str | None = None) -> GeneratedFile:
        try:
            self._validate_text(text, filename)
            tokens = Lexer(text, filename).tokenize()
            unit = Parser(tokens, filename).parse()
            SemanticAnalyzer(filename).analyze(unit)
            stem = base_name or Path(filename).stem
            return CppGenerator(filename).generate(unit, stem)
        except TranslationError as exc:
            self.diagnostics.add(exc.diagnostic)
            raise

    def translate_file(self, path: str | Path, output_dir: str | Path) -> Dict[str, str]:
        path = Path(path)
        output_dir = Path(output_dir)
        self._validate_input_path(path)
        text = path.read_text(encoding="utf-8")
        generated = self.translate_text(text, path.name, path.stem)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            error = TranslationError(Stage.GEN, "OutputDirectory", ru_message("OutputDirectory", str(exc)), path.name, 1, 1)
            self.diagnostics.add(error.diagnostic)
            raise error
        header_path = output_dir / generated.header_name
        source_path = output_dir / generated.source_name
        header_path.write_text(generated.header_code, encoding="utf-8")
        source_path.write_text(generated.source_code, encoding="utf-8")
        return {"header": str(header_path), "source": str(source_path)}

    def _validate_input_path(self, path: Path) -> None:
        name = path.name
        if path.suffix != ".java":
            raise self._validation_error("InvalidInputExtension", name)
        if len(name) > 255:
            raise self._validation_error("FileNameTooLong", name)
        if any(ch in name for ch in '/:*?"<>|'):
            raise self._validation_error("InvalidFileName", name)

    def _validate_text(self, text: str, filename: str) -> None:
        if text == "":
            raise TranslationError(Stage.LEX, "EmptyInput", ru_message("EmptyInput"), filename, 1, 1)
        if text.count("\n") + 1 > 10_000:
            raise TranslationError(Stage.LEX, "SourceTooLarge", ru_message("SourceTooLarge"), filename, 1, 1)

    def _validation_error(self, code: str, filename: str) -> TranslationError:
        error = TranslationError(Stage.LEX, code, ru_message(code), filename, 1, 1)
        self.diagnostics.add(error.diagnostic)
        return error

    def translate_many(self, paths: List[str | Path], output_dir: str | Path) -> dict:
        processed = 0
        failed = 0
        outputs = []
        for path in paths:
            processed += 1
            try:
                outputs.append(self.translate_file(path, output_dir))
            except TranslationError:
                failed += 1
        summary = self.diagnostics.summary()
        return {
            "processed_files": processed,
            "files_with_errors": failed,
            "errors": summary["errors"],
            "warnings": summary["warnings"],
            "outputs": outputs,
        }
