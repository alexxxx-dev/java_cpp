from __future__ import annotations

import re
from typing import List, Optional

from .ast import *
from .diagnostics import Position, Stage, TranslationError, ru_message
from .lexer import Token


MODIFIERS = {"public", "private", "protected", "static", "final"}
TYPE_TOKENS = {"int", "long", "short", "byte", "float", "double", "boolean", "char", "String", "void", "IDENT"}
UNSUPPORTED = {"try", "catch", "finally", "switch", "case", "default", "throw", "throws", "enum", "@", "instanceof"}


class Parser:
    def __init__(self, tokens: List[Token], filename: str) -> None:
        self.tokens = tokens
        self.filename = filename
        self.index = 0
        self.imports: List[str] = []

    def parse(self) -> CompilationUnit:
        decls: List[TypeDecl] = []
        while not self._match("EOF"):
            if self._match("package"):
                self._qualified_name()
                self._consume(";", "expected ';' after package")
                continue
            if self._match("import"):
                self.imports.append(self._qualified_name(allow_star=True))
                self._consume(";", "expected ';' after import")
                continue
            if self._peek().kind in UNSUPPORTED:
                tok = self._peek()
                raise self._error("NotSupported", ru_message("NotSupported", tok.lexeme), tok)
            decls.append(self._type_decl())
        return CompilationUnit(position=Position(1, 1), declarations=decls, imports=self.imports)

    def _qualified_name(self, allow_star: bool = False) -> str:
        parts = [self._consume("IDENT", "expected qualified name").lexeme]
        while self._match("."):
            if allow_star and self._match("*"):
                parts.append("*")
                return ".".join(parts)
            parts.append(self._consume("IDENT", "expected qualified name part").lexeme)
        return ".".join(parts)

    def _type_decl(self) -> TypeDecl:
        mods = self._modifiers()
        if self._match("class"):
            return self._class_decl(mods)
        if self._match("interface"):
            return self._interface_decl(mods)
        tok = self._peek()
        raise self._error("SyntaxError", f"expected class or interface, got '{tok.lexeme}'", tok)

    def _class_decl(self, modifiers: List[str]) -> ClassDecl:
        start = self._previous()
        name = self._consume("IDENT", "expected class name").lexeme
        extends = None
        implements: List[str] = []
        if self._match("extends"):
            extends = self._consume("IDENT", "expected base class name").lexeme
        if self._match("implements"):
            implements.append(self._consume("IDENT", "expected interface name").lexeme)
            while self._match(","):
                implements.append(self._consume("IDENT", "expected interface name").lexeme)
        self._consume("{", "expected '{'")
        members: List[object] = []
        while not self._match("}"):
            if self._peek().kind == "EOF":
                raise self._error("SyntaxError", "expected '}'", self._peek())
            members.append(self._class_member(name))
        return ClassDecl(position=Position(start.line, start.column), modifiers=modifiers, name=name, extends=extends, implements=implements, members=members)

    def _interface_decl(self, modifiers: List[str]) -> InterfaceDecl:
        start = self._previous()
        name = self._consume("IDENT", "expected interface name").lexeme
        self._consume("{", "expected '{'")
        members: List[InterfaceMethodDecl] = []
        while not self._match("}"):
            member_mods = self._modifiers()
            return_type = self._type_ref(allow_void=True)
            member_name = self._consume("IDENT", "expected method name").lexeme
            params = self._parameters()
            end = self._consume(";", "expected ';'")
            members.append(InterfaceMethodDecl(position=Position(end.line, end.column), modifiers=member_mods, return_type=return_type, name=member_name, parameters=params))
        return InterfaceDecl(position=Position(start.line, start.column), modifiers=modifiers, name=name, members=members)

    def _class_member(self, class_name: str) -> object:
        mods = self._modifiers()
        if self._peek().kind == "IDENT" and self._peek().lexeme == class_name and self._peek(1).kind == "(":
            start = self._advance()
            params = self._parameters()
            body = self._block()
            return ConstructorDecl(position=Position(start.line, start.column), modifiers=mods, name=class_name, parameters=params, body=body)
        type_ref = self._type_ref(allow_void=True)
        name_tok = self._consume("IDENT", "expected member name")
        if self._peek().kind == "(":
            params = self._parameters()
            if self._match(";"):
                return MethodDecl(position=Position(name_tok.line, name_tok.column), modifiers=mods, return_type=type_ref, name=name_tok.lexeme, parameters=params, body=None)
            body = self._block()
            return MethodDecl(position=Position(name_tok.line, name_tok.column), modifiers=mods, return_type=type_ref, name=name_tok.lexeme, parameters=params, body=body)
        initializer = None
        if self._match("="):
            initializer = self._expression()
        end = self._consume(";", "expected ';'")
        return FieldDecl(position=Position(end.line, end.column), modifiers=mods, type_ref=type_ref, name=name_tok.lexeme, initializer=initializer)

    def _parameters(self) -> List[Parameter]:
        self._consume("(", "expected '('")
        params: List[Parameter] = []
        if not self._match(")"):
            while True:
                t = self._type_ref(allow_void=False)
                name_tok = self._consume("IDENT", "expected parameter name")
                params.append(Parameter(position=Position(name_tok.line, name_tok.column), type_ref=t, name=name_tok.lexeme))
                if self._match(")"):
                    break
                self._consume(",", "expected ','")
        return params

    def _block(self) -> BlockStmt:
        start = self._consume("{", "expected '{'")
        stmts: List[Stmt] = []
        while not self._match("}"):
            if self._peek().kind == "EOF":
                raise self._error("SyntaxError", "expected '}'", self._peek())
            stmts.append(self._statement())
        return BlockStmt(position=Position(start.line, start.column), statements=stmts)

    def _statement(self) -> Stmt:
        tok = self._peek()
        if tok.kind in UNSUPPORTED:
            raise self._error("NotSupported", f"construct '{tok.lexeme}' is not supported", tok)
        if self._match("{"):
            self.index -= 1
            return self._block()
        if self._match("if"):
            start = self._previous()
            self._consume("(", "expected '('")
            cond = self._expression()
            self._consume(")", "expected ')'")
            then_branch = self._statement()
            else_branch = self._statement() if self._match("else") else None
            return IfStmt(position=Position(start.line, start.column), condition=cond, then_branch=then_branch, else_branch=else_branch)
        if self._match("while"):
            start = self._previous()
            self._consume("(", "expected '('")
            cond = self._expression()
            self._consume(")", "expected ')'")
            return WhileStmt(position=Position(start.line, start.column), condition=cond, body=self._statement())
        if self._match("do"):
            start = self._previous()
            body = self._statement()
            self._consume("while", "expected while")
            self._consume("(", "expected '('")
            cond = self._expression()
            self._consume(")", "expected ')'")
            self._consume(";", "expected ';'")
            return DoWhileStmt(position=Position(start.line, start.column), body=body, condition=cond)
        if self._match("for"):
            start = self._previous()
            self._consume("(", "expected '('")
            init: Optional[Stmt] = None
            if not self._match(";"):
                if self._looks_like_type():
                    init = self._var_decl(require_semicolon=False)
                else:
                    start_expr = self._peek()
                    init = ExprStmt(position=Position(start_expr.line, start_expr.column), expr=self._expression())
                self._consume(";", "expected ';'")
            cond = None
            if not self._match(";"):
                cond = self._expression()
                self._consume(";", "expected ';'")
            update = None
            if not self._match(")"):
                update = self._expression()
                self._consume(")", "expected ')' after for clauses")
            return ForStmt(position=Position(start.line, start.column), init=init, condition=cond, update=update, body=self._statement())
        if self._match("return"):
            start = self._previous()
            expr = None
            if not self._match(";"):
                expr = self._expression()
                self._consume(";", "expected ';'")
            return ReturnStmt(position=Position(start.line, start.column), expr=expr)
        if self._match("break"):
            start = self._previous(); self._consume(";", "expected ';'")
            return BreakStmt(position=Position(start.line, start.column))
        if self._match("continue"):
            start = self._previous(); self._consume(";", "expected ';'")
            return ContinueStmt(position=Position(start.line, start.column))
        if self._looks_like_type():
            return self._var_decl(require_semicolon=True)
        expr = self._expression()
        if isinstance(expr, MemberAccessExpr) and self._member_chain(expr) == "System.out.println" and self._peek().kind != "(":
            raise self._error(
                "SyntaxError",
                ru_message("MissingCallParentheses"),
                self._peek(),
            )
        if isinstance(expr, CallExpr) and isinstance(expr.callee, MemberAccessExpr):
            chain = self._member_chain(expr.callee)
            if chain in {"Systemout.println", "System.outprintln"}:
                raise self._error("SyntaxError", "некорректный вызов вывода", expr.callee.position)
        self._consume(";", "expected ';'")
        return ExprStmt(position=Position(tok.line, tok.column), expr=expr)

    def _var_decl(self, require_semicolon: bool) -> VarDeclStmt:
        start = self._peek()
        t = self._type_ref(allow_void=False)
        name_tok = self._consume("IDENT", "expected variable name")
        initializer = self._expression() if self._match("=") else None
        if require_semicolon and initializer is not None and self._peek().kind in {"STRING_LITERAL", "INT_LITERAL", "FLOAT_LITERAL", "true", "false", "IDENT"}:
            token = self._peek()
            raise TranslationError(Stage.SEM, "TypeMismatch", "несовместимые типы", self.filename, token.line, token.column)
        if require_semicolon:
            self._consume(";", "expected ';'")
        return VarDeclStmt(position=Position(start.line, start.column), type_ref=t, name=name_tok.lexeme, initializer=initializer)

    def _type_ref(self, allow_void: bool) -> TypeRef:
        tok = self._peek()
        if tok.kind not in TYPE_TOKENS or (tok.kind == "void" and not allow_void):
            raise self._error("SyntaxError", f"expected type, got '{tok.lexeme}'", tok)
        self._advance()
        name = tok.lexeme
        dims = 0
        while self._match("["):
            self._consume("]", "expected ']' after '['")
            dims += 1
        return TypeRef(name=name, dimensions=dims)

    def _base_type_ref(self, allow_void: bool) -> TypeRef:
        tok = self._peek()
        if tok.kind not in TYPE_TOKENS or (tok.kind == "void" and not allow_void):
            raise self._error("SyntaxError", f"expected type, got '{tok.lexeme}'", tok)
        self._advance()
        return TypeRef(name=tok.lexeme, dimensions=0)

    def _expression(self) -> Expr:
        return self._assignment()

    def _assignment(self) -> Expr:
        expr = self._logical_or()
        if self._match("=", "+=", "-="):
            op_tok = self._previous()
            value = self._assignment()
            return AssignExpr(position=Position(op_tok.line, op_tok.column), target=expr, operator=op_tok.kind, value=value)
        return expr

    def _logical_or(self) -> Expr:
        expr = self._logical_and()
        while self._match("||"):
            op = self._previous(); right = self._logical_and()
            expr = BinaryExpr(position=Position(op.line, op.column), left=expr, operator=op.kind, right=right)
        return expr

    def _logical_and(self) -> Expr:
        expr = self._equality()
        while self._match("&&"):
            op = self._previous(); right = self._equality()
            expr = BinaryExpr(position=Position(op.line, op.column), left=expr, operator=op.kind, right=right)
        return expr

    def _equality(self) -> Expr:
        expr = self._comparison()
        while self._match("==", "!="):
            op = self._previous(); right = self._comparison()
            expr = BinaryExpr(position=Position(op.line, op.column), left=expr, operator=op.kind, right=right)
        return expr

    def _comparison(self) -> Expr:
        expr = self._term()
        while self._match("<", "<=", ">", ">="):
            op = self._previous(); right = self._term()
            expr = BinaryExpr(position=Position(op.line, op.column), left=expr, operator=op.kind, right=right)
        return expr

    def _term(self) -> Expr:
        expr = self._factor()
        while self._match("+", "-"):
            op = self._previous(); right = self._factor()
            expr = BinaryExpr(position=Position(op.line, op.column), left=expr, operator=op.kind, right=right)
        return expr

    def _factor(self) -> Expr:
        expr = self._unary()
        while self._match("*", "/", "%"):
            op = self._previous(); right = self._unary()
            expr = BinaryExpr(position=Position(op.line, op.column), left=expr, operator=op.kind, right=right)
        return expr

    def _unary(self) -> Expr:
        if self._match("!", "+", "-", "++", "--"):
            op = self._previous()
            return UnaryExpr(position=Position(op.line, op.column), operator=op.kind, operand=self._unary())
        return self._postfix()

    def _postfix(self) -> Expr:
        expr = self._primary()
        while True:
            if self._match("."):
                ident = self._consume("IDENT", "expected member name")
                expr = MemberAccessExpr(position=Position(ident.line, ident.column), target=expr, member=ident.lexeme)
                continue
            if self._match("("):
                args: List[Expr] = []
                if not self._match(")"):
                    while True:
                        args.append(self._expression())
                        if self._match(")"):
                            break
                        self._consume(",", "expected ','")
                expr = CallExpr(position=expr.position, callee=expr, arguments=args)
                continue
            if self._match("["):
                index = self._expression()
                end = self._consume("]", "expected ']' after index")
                expr = IndexExpr(position=Position(end.line, end.column), target=expr, index=index)
                continue
            if self._match("++", "--"):
                op = self._previous()
                expr = PostfixExpr(position=Position(op.line, op.column), operand=expr, operator=op.kind)
                continue
            break
        return expr

    def _primary(self) -> Expr:
        tok = self._peek()
        if self._match("INT_LITERAL"):
            return LiteralExpr(position=Position(tok.line, tok.column), value=tok.lexeme, kind="int")
        if self._match("FLOAT_LITERAL"):
            return LiteralExpr(position=Position(tok.line, tok.column), value=tok.lexeme, kind="float")
        if self._match("STRING_LITERAL"):
            return LiteralExpr(position=Position(tok.line, tok.column), value=tok.lexeme, kind="String")
        if self._match("CHAR_LITERAL"):
            return LiteralExpr(position=Position(tok.line, tok.column), value=tok.lexeme, kind="char")
        if self._match("true", "false"):
            return LiteralExpr(position=Position(tok.line, tok.column), value=tok.lexeme, kind="boolean")
        if self._match("null"):
            return LiteralExpr(position=Position(tok.line, tok.column), value=tok.lexeme, kind="null")
        if self._match("this"):
            return ThisExpr(position=Position(tok.line, tok.column))
        if self._match("IDENT"):
            return NameExpr(position=Position(tok.line, tok.column), name=tok.lexeme)
        if self._match("new"):
            start = self._previous()
            type_ref = self._base_type_ref(allow_void=False)
            if self._match("("):
                args: List[Expr] = []
                if not self._match(")"):
                    while True:
                        args.append(self._expression())
                        if self._match(")"):
                            break
                        self._consume(",", "expected ','")
                return NewExpr(position=Position(start.line, start.column), type_ref=type_ref, arguments=args, array_size=None)
            if self._match("["):
                size = self._expression()
                self._consume("]", "expected ']' after array size")
                return NewExpr(position=Position(start.line, start.column), type_ref=type_ref, arguments=[], array_size=size)
            raise self._error("SyntaxError", "expected constructor call or array allocation after new", self._peek())
        if self._match("{"):
            start = self._previous()
            elements: List[Expr] = []
            if not self._match("}"):
                while True:
                    elements.append(self._expression())
                    if self._match("}"):
                        break
                    self._consume(",", "expected ',' in array initializer")
            return ArrayLiteralExpr(position=Position(start.line, start.column), elements=elements)
        if self._match("("):
            expr = self._expression()
            self._consume(")", "expected ')'")
            return expr
        raise self._error("SyntaxError", f"unexpected token '{tok.lexeme}'", tok)

    def _modifiers(self) -> List[str]:
        result: List[str] = []
        while self._peek().kind in MODIFIERS:
            result.append(self._advance().lexeme)
        return result

    def _looks_like_type(self) -> bool:
        first = self._peek()
        second = self._peek(1)
        if first.kind in {"int", "long", "short", "byte", "float", "double", "boolean", "char", "String"}:
            return True
        if first.kind == "IDENT" and second.kind == "IDENT":
            return True
        if first.kind == "IDENT" and second.kind == "[":
            return self._peek(2).kind == "]" and self._peek(3).kind == "IDENT"
        return False

    def _match(self, *kinds: str) -> bool:
        if self._peek().kind in kinds:
            self._advance()
            return True
        return False

    def _consume(self, kind: str, message: str) -> Token:
        if self._peek().kind == kind:
            return self._advance()
        raise self._error("SyntaxError", message, self._peek())

    def _advance(self) -> Token:
        tok = self.tokens[self.index]
        self.index += 1
        return tok

    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.index + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _previous(self) -> Token:
        return self.tokens[self.index - 1]

    def _error(self, code: str, message: str, token: Token | Position) -> TranslationError:
        if code == "SyntaxError":
            if message != ru_message("MissingCallParentheses"):
                if not any(ord(ch) > 127 for ch in message):
                    message = ru_message(code, self._localize_syntax_detail(message))
        elif code == "NotSupported":
            message = ru_message(code, message)
        return TranslationError(Stage.SYN, code, message, self.filename, token.line, token.column)

    def _member_chain(self, expr: Expr) -> str:
        if isinstance(expr, NameExpr):
            return expr.name
        if isinstance(expr, MemberAccessExpr):
            return f"{self._member_chain(expr.target)}.{expr.member}"
        return ""

    def _localize_syntax_detail(self, message: str) -> str:
        simple = {
            "expected ';'": "ожидался символ ';'",
            "expected ','": "ожидался символ ','",
            "expected '{'": "ожидался символ '{'",
            "expected '}'": "ожидался символ '}'",
            "expected '('": "ожидался символ '('",
            "expected ')'": "ожидался символ ')'",
            "expected while": "ожидалось ключевое слово while",
            "expected ')' after for clauses": "ожидался символ ')' после заголовка for",
            "expected ';' after import": "ожидался символ ';' после import",
            "expected ';' after package": "ожидался символ ';' после package",
            "expected member name": "ожидалось имя члена класса",
            "expected variable name": "ожидалось имя переменной",
            "expected parameter name": "ожидалось имя параметра",
            "expected class name": "ожидалось имя класса",
            "expected interface name": "ожидалось имя интерфейса",
            "expected method name": "ожидалось имя метода",
            "expected base class name": "ожидалось имя базового класса",
            "expected qualified name": "ожидалось полное имя",
            "expected qualified name part": "ожидалась следующая часть полного имени",
            "expected constructor call or array allocation after new": "после new ожидался вызов конструктора или создание массива",
            "expected ',' in array initializer": "в инициализаторе массива ожидался символ ','",
            "expected ']' after '['": "ожидался символ ']'",
            "incorrect output call": "некорректный вызов вывода",
        }
        if message in simple:
            return simple[message]
        if match := re.fullmatch(r"expected class or interface, got '(.+)'", message):
            return f"ожидалось объявление class или interface, найдено '{match.group(1)}'"
        if match := re.fullmatch(r"expected type, got '(.+)'", message):
            return f"ожидался тип, найдено '{match.group(1)}'"
        if match := re.fullmatch(r"unexpected token '(.+)'", message):
            return f"неожиданный токен '{match.group(1)}'"
        return message
