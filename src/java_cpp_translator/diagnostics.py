from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class Stage(str, Enum):
    LEX = "LEX"
    SYN = "SYN"
    SEM = "SEM"
    TR = "TR"
    GEN = "GEN"


@dataclass(slots=True)
class Position:
    line: int
    column: int


@dataclass(slots=True)
class Diagnostic:
    stage: Stage
    level: str
    code: str
    message: str
    filename: str
    position: Position
    context: Optional[str] = None

    def format(self) -> str:
        ctx = f" [{self.context}]" if self.context else ""
        return (
            f"{self.filename}:{self.position.line}:{self.position.column} "
            f"{self.stage.value} {self.level} {self.code}: {self.message}{ctx}"
        )

    def format_ru(self) -> str:
        ctx = f" [контекст: {self.context}]" if self.context else ""
        stage_names = {
            Stage.LEX: "лексический анализ",
            Stage.SYN: "синтаксический анализ",
            Stage.SEM: "семантический анализ",
            Stage.TR: "трансляция",
            Stage.GEN: "генерация C++",
        }
        level = "Ошибка" if self.level == "Error" else "Предупреждение"
        return (
            f"{self.filename}:{self.position.line}:{self.position.column} "
            f"{self.stage.value} {level} {self.code}: {self.message}{ctx} "
            f"({stage_names.get(self.stage, self.stage.value)})"
        )


RU_MESSAGES = {
    "DuplicateField": "поле уже объявлено",
    "DuplicateParameter": "параметр уже объявлен",
    "DuplicateType": "тип уже объявлен",
    "DuplicateVariable": "переменная уже объявлена в этой области видимости",
    "DivisionByZero": "обнаружено деление на ноль",
    "FileNameTooLong": "имя файла не должно быть длиннее 255 символов",
    "InvalidCharacter": "недопустимый символ в исходном коде",
    "InvalidFileName": "имя входного файла содержит недопустимые символы",
    "InvalidInputExtension": "входной файл должен иметь расширение .java",
    "InvalidReturn": "оператор return не соответствует типу метода",
    "MethodSignatureMismatch": "аргументы метода не подходят ни к одной сигнатуре",
    "MissingCallParentheses": "отсутствуют круглые скобки при вызове метода",
    "MissingReturn": "не все пути выполнения возвращают значение",
    "NotSupported": "конструкция Java не поддерживается транслятором",
    "NotSupportedFinalize": "метод finalize не поддерживается",
    "OutputDirectory": "не удалось подготовить каталог вывода",
    "SourceTooLarge": "исходный файл не должен превышать 10 000 строк",
    "SyntaxError": "синтаксическая ошибка",
    "TypeMismatch": "несовместимые типы",
    "UndefinedIdentifier": "идентификатор не объявлен",
    "UndefinedMember": "член типа не найден",
    "UndefinedMethod": "метод не объявлен",
    "UndefinedType": "тип не объявлен",
    "UnterminatedChar": "символьный литерал не закрыт",
    "UnterminatedComment": "многострочный комментарий не закрыт",
    "UnterminatedString": "строковый литерал не закрыт",
    "EmptyInput": "входной файл пустой",
}


def ru_message(code: str, detail: str | None = None) -> str:
    base = RU_MESSAGES.get(code, "ошибка трансляции")
    return f"{base}: {detail}" if detail else base


class TranslationError(Exception):
    def __init__(
        self,
        stage: Stage,
        code: str,
        message: str,
        filename: str,
        line: int,
        column: int,
        context: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.diagnostic = Diagnostic(
            stage=stage,
            level="Error",
            code=code,
            message=message,
            filename=filename,
            position=Position(line, column),
            context=context,
        )


class DiagnosticBag:
    def __init__(self) -> None:
        self.items: List[Diagnostic] = []

    def add(self, diagnostic: Diagnostic) -> None:
        self.items.append(diagnostic)

    def extend(self, diagnostics: List[Diagnostic]) -> None:
        self.items.extend(diagnostics)

    @property
    def has_errors(self) -> bool:
        return any(item.level == "Error" for item in self.items)

    def summary(self) -> dict:
        return {
            "errors": sum(1 for item in self.items if item.level == "Error"),
            "warnings": sum(1 for item in self.items if item.level != "Error"),
        }
