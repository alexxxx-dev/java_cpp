from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .diagnostics import Stage, TranslationError, ru_message

KEYWORDS = {
    "abstract", "boolean", "break", "byte", "case", "catch", "char", "class",
    "continue", "default", "do", "double", "else", "extends", "final",
    "finally", "float", "for", "if", "implements", "import", "int",
    "interface", "long", "new", "package", "private", "protected", "public",
    "return", "short", "static", "switch", "synchronized", "this", "throw",
    "throws", "transient", "try", "void", "volatile", "while", "String",
    "null", "true", "false",
}

TWO_CHAR = {"++", "--", "+=", "-=", "==", "!=", "<=", ">=", "&&", "||"}
ONE_CHAR = set("=+-*/%<>!.,;:(){}[]")


@dataclass(slots=True)
class Token:
    kind: str
    lexeme: str
    line: int
    column: int


class Lexer:
    def __init__(self, text: str, filename: str) -> None:
        self.text = text
        self.filename = filename
        self.index = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while not self._eof():
            ch = self._peek()
            if ch in " \t\r":
                self._advance()
                continue
            if ch == "\n":
                self._advance_line()
                continue
            if ch == "/" and self._peek(1) == "/":
                while not self._eof() and self._peek() != "\n":
                    self._advance()
                continue
            if ch == "/" and self._peek(1) == "*":
                self._advance(); self._advance()
                while not self._eof() and not (self._peek() == "*" and self._peek(1) == "/"):
                    if self._peek() == "\n":
                        self._advance_line()
                    else:
                        self._advance()
                if self._eof():
                    raise TranslationError(Stage.LEX, "UnterminatedComment", ru_message("UnterminatedComment"), self.filename, self.line, self.column)
                self._advance(); self._advance()
                continue
            if ch.isalpha() or ch in "_$":
                tokens.append(self._identifier())
                continue
            if ch.isdigit():
                tokens.append(self._number())
                continue
            if ch == '"':
                tokens.append(self._string())
                continue
            if ch == "'":
                tokens.append(self._char())
                continue
            pair = ch + self._peek(1)
            if pair in TWO_CHAR:
                tokens.append(Token(pair, pair, self.line, self.column))
                self._advance(); self._advance()
                continue
            if ch in ONE_CHAR:
                tokens.append(Token(ch, ch, self.line, self.column))
                self._advance()
                continue
            raise TranslationError(Stage.LEX, "InvalidCharacter", ru_message("InvalidCharacter", repr(ch)), self.filename, self.line, self.column)
        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens

    def _identifier(self) -> Token:
        line, col = self.line, self.column
        buf = []
        while not self._eof() and (self._peek().isalnum() or self._peek() in "_$"):
            buf.append(self._peek())
            self._advance()
        text = "".join(buf)
        kind = text if text in KEYWORDS else "IDENT"
        return Token(kind, text, line, col)

    def _number(self) -> Token:
        line, col = self.line, self.column
        buf = []
        has_dot = False
        while not self._eof() and (self._peek().isdigit() or (self._peek() == "." and not has_dot)):
            if self._peek() == ".":
                has_dot = True
            buf.append(self._peek())
            self._advance()
        text = "".join(buf)
        return Token("FLOAT_LITERAL" if has_dot else "INT_LITERAL", text, line, col)

    def _string(self) -> Token:
        line, col = self.line, self.column
        buf = ['"']
        self._advance()
        while not self._eof() and self._peek() != '"':
            if self._peek() == "\n":
                raise TranslationError(Stage.LEX, "UnterminatedString", ru_message("UnterminatedString"), self.filename, self.line, self.column)
            if self._peek() == "\\":
                buf.append(self._peek())
                self._advance()
                if self._eof():
                    break
            buf.append(self._peek())
            self._advance()
        if self._eof():
            raise TranslationError(Stage.LEX, "UnterminatedString", ru_message("UnterminatedString"), self.filename, line, col)
        buf.append('"')
        self._advance()
        return Token("STRING_LITERAL", "".join(buf), line, col)

    def _char(self) -> Token:
        line, col = self.line, self.column
        buf = ["'"]
        self._advance()
        while not self._eof() and self._peek() != "'":
            if self._peek() == "\n":
                raise TranslationError(Stage.LEX, "UnterminatedChar", ru_message("UnterminatedChar"), self.filename, self.line, self.column)
            if self._peek() == "\\":
                buf.append(self._peek())
                self._advance()
                if self._eof():
                    break
            buf.append(self._peek())
            self._advance()
        if self._eof():
            raise TranslationError(Stage.LEX, "UnterminatedChar", ru_message("UnterminatedChar"), self.filename, line, col)
        buf.append("'")
        self._advance()
        return Token("CHAR_LITERAL", "".join(buf), line, col)

    def _peek(self, offset: int = 0) -> str:
        idx = self.index + offset
        return self.text[idx] if idx < len(self.text) else "\0"

    def _advance(self) -> None:
        self.index += 1
        self.column += 1

    def _advance_line(self) -> None:
        self.index += 1
        self.line += 1
        self.column = 1

    def _eof(self) -> bool:
        return self.index >= len(self.text)
