from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Optional

from .ast import *
from .diagnostics import Stage, TranslationError, ru_message


PRIMITIVES = {"int", "long", "short", "byte", "float", "double", "boolean", "char", "void"}
REFERENCE_NAMES = {"String", "Scanner"}


@dataclass
class MethodSig:
    return_type: TypeRef
    parameters: List[TypeRef]
    is_static: bool = False


@dataclass
class ClassInfo:
    name: str
    kind: str
    fields: Dict[str, TypeRef]
    methods: Dict[str, List[MethodSig]]
    extends: Optional[str] = None
    implements: List[str] = None


class Scope:
    def __init__(self, parent: Optional["Scope"] = None) -> None:
        self.parent = parent
        self.symbols: Dict[str, TypeRef] = {}

    def define(self, name: str, type_ref: TypeRef) -> bool:
        if name in self.symbols:
            return False
        self.symbols[name] = type_ref
        return True

    def lookup(self, name: str) -> Optional[TypeRef]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None


class SemanticAnalyzer:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.classes: Dict[str, ClassInfo] = {}
        self.current_class: Optional[ClassInfo] = None
        self.current_method: Optional[MethodSig] = None

    def analyze(self, unit: CompilationUnit) -> CompilationUnit:
        self.classes["Scanner"] = ClassInfo(
            "Scanner",
            "class",
            {},
            {
                "nextInt": [MethodSig(TypeRef("int"), [])],
                "nextLine": [MethodSig(TypeRef("String"), [])],
                "nextDouble": [MethodSig(TypeRef("double"), [])],
                "close": [MethodSig(TypeRef("void"), [])],
            },
            None,
            [],
        )
        self._collect_types(unit)
        for decl in unit.declarations:
            if isinstance(decl, ClassDecl):
                self._analyze_class(decl)
            else:
                self._analyze_interface(decl)
        return unit

    def _collect_types(self, unit: CompilationUnit) -> None:
        for decl in unit.declarations:
            if decl.name in self.classes:
                raise self._error("DuplicateType", f"type '{decl.name}' already declared", decl.position.line, decl.position.column, decl.name)
            if isinstance(decl, ClassDecl):
                fields: Dict[str, TypeRef] = {}
                methods: Dict[str, List[MethodSig]] = {}
                for member in decl.members:
                    if isinstance(member, FieldDecl):
                        if member.name in fields:
                            raise self._error("DuplicateField", f"field '{member.name}' already declared", member.position.line, member.position.column, decl.name)
                        fields[member.name] = member.type_ref
                    elif isinstance(member, MethodDecl):
                        methods.setdefault(member.name, []).append(MethodSig(member.return_type, [p.type_ref for p in member.parameters], "static" in member.modifiers))
                    elif isinstance(member, ConstructorDecl):
                        methods.setdefault(decl.name, []).append(MethodSig(TypeRef("void"), [p.type_ref for p in member.parameters], False))
                self.classes[decl.name] = ClassInfo(decl.name, "class", fields, methods, decl.extends, decl.implements)
            else:
                methods = {m.name: [MethodSig(m.return_type, [p.type_ref for p in m.parameters], False)] for m in decl.members}
                self.classes[decl.name] = ClassInfo(decl.name, "interface", {}, methods, None, [])

    def _analyze_interface(self, decl: InterfaceDecl) -> None:
        return

    def _analyze_class(self, decl: ClassDecl) -> None:
        self.current_class = self.classes[decl.name]
        if decl.extends and decl.extends not in self.classes:
            raise self._error("UndefinedType", f"base class '{decl.extends}' is not defined", decl.position.line, decl.position.column, decl.name)
        for interface in decl.implements:
            if interface not in self.classes:
                raise self._error("UndefinedType", f"interface '{interface}' is not defined", decl.position.line, decl.position.column, decl.name)
        for member in decl.members:
            if isinstance(member, FieldDecl) and member.initializer:
                scope = Scope()
                self._check_expr(member.initializer, scope)
                self._ensure_assignable(member.type_ref, member.initializer.inferred_type, member.position.line, member.position.column, decl.name)
            elif isinstance(member, ConstructorDecl):
                self.current_method = MethodSig(TypeRef("void"), [p.type_ref for p in member.parameters], False)
                class_scope = Scope()
                for field_name, field_type in self.current_class.fields.items():
                    class_scope.define(field_name, field_type)
                scope = Scope(class_scope)
                for p in member.parameters:
                    if not scope.define(p.name, p.type_ref):
                        raise self._error("DuplicateParameter", f"parameter '{p.name}' already declared", p.position.line, p.position.column, decl.name)
                self._check_stmt(member.body, scope)
            elif isinstance(member, MethodDecl) and member.body is not None:
                self.current_method = MethodSig(member.return_type, [p.type_ref for p in member.parameters], "static" in member.modifiers)
                class_scope = Scope()
                for field_name, field_type in self.current_class.fields.items():
                    class_scope.define(field_name, field_type)
                scope = Scope(class_scope)
                for p in member.parameters:
                    if not scope.define(p.name, p.type_ref):
                        raise self._error("DuplicateParameter", f"parameter '{p.name}' already declared", p.position.line, p.position.column, decl.name)
                self._check_stmt(member.body, scope)
                if member.return_type.name != "void" and not self._block_returns(member.body):
                    raise self._error("MissingReturn", ru_message("MissingReturn"), member.position.line, member.position.column, decl.name)
                self._validate_main(member, decl)

    def _check_stmt(self, stmt: Stmt, scope: Scope) -> None:
        if isinstance(stmt, BlockStmt):
            block_scope = Scope(scope)
            for s in stmt.statements:
                self._check_stmt(s, block_scope)
            return
        if isinstance(stmt, VarDeclStmt):
            if not scope.define(stmt.name, stmt.type_ref):
                raise self._error("DuplicateVariable", f"variable '{stmt.name}' already declared", stmt.position.line, stmt.position.column, self.current_class.name if self.current_class else None)
            if stmt.initializer:
                self._check_expr(stmt.initializer, scope)
                self._ensure_assignable(stmt.type_ref, stmt.initializer.inferred_type, stmt.position.line, stmt.position.column, self.current_class.name if self.current_class else None)
            return
        if isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr, scope); return
        if isinstance(stmt, IfStmt):
            self._check_expr(stmt.condition, scope)
            self._ensure_boolean(stmt.condition, stmt.position.line, stmt.position.column)
            self._check_stmt(stmt.then_branch, Scope(scope))
            if stmt.else_branch:
                self._check_stmt(stmt.else_branch, Scope(scope))
            return
        if isinstance(stmt, WhileStmt):
            self._check_expr(stmt.condition, scope); self._ensure_boolean(stmt.condition, stmt.position.line, stmt.position.column)
            self._check_stmt(stmt.body, Scope(scope)); return
        if isinstance(stmt, DoWhileStmt):
            self._check_stmt(stmt.body, Scope(scope)); self._check_expr(stmt.condition, scope); self._ensure_boolean(stmt.condition, stmt.position.line, stmt.position.column); return
        if isinstance(stmt, ForStmt):
            loop_scope = Scope(scope)
            if stmt.init:
                self._check_stmt(stmt.init, loop_scope)
            if stmt.condition:
                self._check_expr(stmt.condition, loop_scope); self._ensure_boolean(stmt.condition, stmt.position.line, stmt.position.column)
            if stmt.update:
                self._check_expr(stmt.update, loop_scope)
            self._check_stmt(stmt.body, loop_scope)
            return
        if isinstance(stmt, ReturnStmt):
            expected = self.current_method.return_type if self.current_method else TypeRef("void")
            if expected.name == "void":
                if stmt.expr is not None:
                    raise self._error("InvalidReturn", "void method cannot return a value", stmt.position.line, stmt.position.column, self.current_class.name if self.current_class else None)
            else:
                if stmt.expr is None:
                    raise self._error("InvalidReturn", "non-void method must return a value", stmt.position.line, stmt.position.column, self.current_class.name if self.current_class else None)
                self._check_expr(stmt.expr, scope)
                self._ensure_assignable(expected, stmt.expr.inferred_type, stmt.position.line, stmt.position.column, self.current_class.name if self.current_class else None)
            return

    def _check_expr(self, expr: Expr, scope: Scope) -> TypeRef:
        if isinstance(expr, LiteralExpr):
            expr.inferred_type = TypeRef(expr.kind)
            return expr.inferred_type
        if isinstance(expr, ThisExpr):
            expr.inferred_type = TypeRef(self.current_class.name)
            return expr.inferred_type
        if isinstance(expr, NameExpr):
            t = scope.lookup(expr.name)
            if t is None:
                raise self._error("UndefinedIdentifier", f"identifier '{expr.name}' is not defined", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            expr.inferred_type = t
            return t
        if isinstance(expr, UnaryExpr):
            operand_t = self._check_expr(expr.operand, scope)
            if expr.operator == "!":
                if operand_t.name != "boolean":
                    raise self._error("TypeMismatch", "operator '!' requires boolean", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
                expr.inferred_type = TypeRef("boolean")
            else:
                expr.inferred_type = operand_t
            return expr.inferred_type
        if isinstance(expr, PostfixExpr):
            operand_t = self._check_expr(expr.operand, scope)
            if expr.operator in {"++", "--"} and not self._is_numeric(operand_t):
                raise self._error("TypeMismatch", ru_message("TypeMismatch", f"оператор '{expr.operator}' требует числовой операнд"), expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            expr.inferred_type = operand_t
            return expr.inferred_type
        if isinstance(expr, BinaryExpr):
            lt = self._check_expr(expr.left, scope)
            rt = self._check_expr(expr.right, scope)
            if expr.operator in {"+", "-", "*", "/", "%"}:
                if expr.operator in {"/", "%"} and self._is_zero_literal(expr.right):
                    raise self._error("DivisionByZero", ru_message("DivisionByZero"), expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
                if expr.operator == "+" and (lt.name == "String" or rt.name == "String"):
                    expr.inferred_type = TypeRef("String")
                elif not self._is_numeric(lt) or not self._is_numeric(rt):
                    raise self._error("TypeMismatch", f"operator '{expr.operator}' requires numeric operands", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
                else:
                    expr.inferred_type = self._wider_numeric(lt, rt)
            elif expr.operator in {"<", "<=", ">", ">="}:
                if not self._is_numeric(lt) or not self._is_numeric(rt):
                    raise self._error("TypeMismatch", f"operator '{expr.operator}' requires numeric operands", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
                expr.inferred_type = TypeRef("boolean")
            elif expr.operator in {"==", "!="}:
                expr.inferred_type = TypeRef("boolean")
            elif expr.operator in {"&&", "||"}:
                if lt.name != "boolean" or rt.name != "boolean":
                    raise self._error("TypeMismatch", f"operator '{expr.operator}' requires boolean operands", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
                expr.inferred_type = TypeRef("boolean")
            return expr.inferred_type
        if isinstance(expr, AssignExpr):
            target_t = self._check_expr(expr.target, scope)
            value_t = self._check_expr(expr.value, scope)
            self._ensure_assignable(target_t, value_t, expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            expr.inferred_type = target_t
            return target_t
        if isinstance(expr, MemberAccessExpr):
            if self._is_system_chain(expr):
                expr.inferred_type = TypeRef("System")
                return expr.inferred_type
            target_t = self._check_expr(expr.target, scope)
            info = self.classes.get(target_t.name)
            if not info:
                raise self._error("UndefinedType", f"type '{target_t.name}' is not defined", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            if expr.member in info.fields:
                expr.inferred_type = info.fields[expr.member]
                return expr.inferred_type
            if expr.member in info.methods:
                expr.inferred_type = info.methods[expr.member][0].return_type
                return expr.inferred_type
            raise self._error("UndefinedMember", f"member '{expr.member}' not found in type '{target_t.name}'", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
        if isinstance(expr, CallExpr):
            if isinstance(expr.callee, MemberAccessExpr) and self._member_chain(expr.callee) == "System.out.println":
                for arg in expr.arguments:
                    self._check_expr(arg, scope)
                expr.inferred_type = TypeRef("void")
                return expr.inferred_type
            if isinstance(expr.callee, MemberAccessExpr):
                target_t = self._check_expr(expr.callee.target, scope)
                info = self.classes.get(target_t.name)
                if not info or expr.callee.member not in info.methods:
                    raise self._error("UndefinedMethod", f"method '{expr.callee.member}' not found in type '{target_t.name}'", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
                candidates = info.methods[expr.callee.member]
            elif isinstance(expr.callee, NameExpr):
                if not self.current_class or expr.callee.name not in self.current_class.methods:
                    raise self._error("UndefinedMethod", f"method '{expr.callee.name}' is not defined", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
                candidates = self.current_class.methods[expr.callee.name]
            else:
                raise self._error("NotSupported", "unsupported call target", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            arg_types = [self._check_expr(arg, scope) for arg in expr.arguments]
            for candidate in candidates:
                if len(candidate.parameters) != len(arg_types):
                    continue
                if all(self._is_assignable(p, a) for p, a in zip(candidate.parameters, arg_types)):
                    expr.inferred_type = candidate.return_type
                    return expr.inferred_type
            raise self._error("MethodSignatureMismatch", "method arguments are not compatible with any overload", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
        if isinstance(expr, NewExpr):
            if expr.type_ref.name == "Scanner":
                for arg in expr.arguments:
                    if not self._is_system_chain(arg):
                        self._check_expr(arg, scope)
                expr.inferred_type = expr.type_ref
                return expr.inferred_type
            if expr.type_ref.name == "finalize":
                raise self._error("NotSupportedFinalize", "finalize is not supported", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            if expr.type_ref.name not in PRIMITIVES and expr.type_ref.name not in self.classes and expr.type_ref.name != "String":
                raise self._error("UndefinedType", f"type '{expr.type_ref.name}' is not defined", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            if expr.array_size:
                self._check_expr(expr.array_size, scope)
                expr.inferred_type = TypeRef(expr.type_ref.name, expr.type_ref.dimensions + 1)
            else:
                for arg in expr.arguments:
                    self._check_expr(arg, scope)
                expr.inferred_type = expr.type_ref
            return expr.inferred_type
        if isinstance(expr, IndexExpr):
            target_t = self._check_expr(expr.target, scope)
            self._check_expr(expr.index, scope)
            if target_t.dimensions < 1:
                raise self._error("TypeMismatch", "indexing requires an array", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            expr.inferred_type = TypeRef(target_t.name, target_t.dimensions - 1)
            return expr.inferred_type
        if isinstance(expr, ArrayLiteralExpr):
            element_type: Optional[TypeRef] = None
            for element in expr.elements:
                current = self._check_expr(element, scope)
                if element_type is None:
                    element_type = current
                elif not self._is_assignable(element_type, current):
                    raise self._error("TypeMismatch", ru_message("TypeMismatch", "элементы массива имеют разные типы"), expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)
            expr.inferred_type = TypeRef(element_type.name if element_type else "int", 1)
            return expr.inferred_type
        raise self._error("NotSupported", f"expression '{type(expr).__name__}' is not supported", expr.position.line, expr.position.column, self.current_class.name if self.current_class else None)

    def _ensure_boolean(self, expr: Expr, line: int, col: int) -> None:
        if expr.inferred_type is None or expr.inferred_type.name != "boolean":
            raise self._error("TypeMismatch", "condition must have boolean type", line, col, self.current_class.name if self.current_class else None)

    def _ensure_assignable(self, expected: TypeRef, actual: Optional[TypeRef], line: int, col: int, context: Optional[str]) -> None:
        if actual is None or not self._is_assignable(expected, actual):
            actual_name = self._type_name(actual) if actual else "unknown"
            raise self._error("TypeMismatch", f"cannot assign value of type '{actual_name}' to '{self._type_name(expected)}'", line, col, context)

    def _is_assignable(self, expected: TypeRef, actual: TypeRef) -> bool:
        if expected.name == actual.name and expected.dimensions == actual.dimensions:
            return True
        if actual.name == "null" and self._is_reference(expected):
            return True
        if self._is_numeric(expected) and self._is_numeric(actual):
            order = ["byte", "short", "int", "long", "float", "double"]
            return order.index(actual.name) <= order.index(expected.name)
        if expected.name in self.classes and actual.name in self.classes:
            if expected.name == actual.name:
                return True
            current = self.classes[actual.name].extends
            while current:
                if current == expected.name:
                    return True
                current = self.classes.get(current).extends if self.classes.get(current) else None
        return False

    def _is_numeric(self, t: TypeRef) -> bool:
        return t.name in {"byte", "short", "int", "long", "float", "double", "char"} and t.dimensions == 0

    def _is_reference(self, t: TypeRef) -> bool:
        return t.dimensions > 0 or t.name in REFERENCE_NAMES or t.name in self.classes

    def _wider_numeric(self, a: TypeRef, b: TypeRef) -> TypeRef:
        order = ["byte", "short", "char", "int", "long", "float", "double"]
        return TypeRef(order[max(order.index(a.name), order.index(b.name))])

    def _error(self, code: str, message: str, line: int, column: int, context: Optional[str]) -> TranslationError:
        if message == "" or code in {
            "DuplicateField", "DuplicateParameter", "DuplicateType", "DuplicateVariable",
            "InvalidReturn", "MethodSignatureMismatch", "NotSupported", "NotSupportedFinalize",
            "TypeMismatch", "UndefinedIdentifier", "UndefinedMember", "UndefinedMethod", "UndefinedType",
        }:
            if not any(ord(ch) > 127 for ch in message):
                message = ru_message(code, self._localize_semantic_detail(message))
        return TranslationError(Stage.SEM, code, message, self.filename, line, column, context)

    def _block_returns(self, block: BlockStmt) -> bool:
        for stmt in block.statements:
            if isinstance(stmt, ReturnStmt):
                return True
            if isinstance(stmt, BlockStmt) and self._block_returns(stmt):
                return True
            if isinstance(stmt, IfStmt) and self._stmt_returns(stmt.then_branch) and stmt.else_branch and self._stmt_returns(stmt.else_branch):
                return True
        return False

    def _stmt_returns(self, stmt: Stmt) -> bool:
        if isinstance(stmt, ReturnStmt):
            return True
        if isinstance(stmt, BlockStmt):
            return self._block_returns(stmt)
        if isinstance(stmt, IfStmt):
            return bool(stmt.else_branch and self._stmt_returns(stmt.then_branch) and self._stmt_returns(stmt.else_branch))
        return False

    def _validate_main(self, member: MethodDecl, decl: ClassDecl) -> None:
        if member.name != "main":
            return
        is_valid = (
            "public" in member.modifiers
            and "static" in member.modifiers
            and member.return_type.name == "void"
            and len(member.parameters) == 1
            and member.parameters[0].type_ref.name == "String"
            and member.parameters[0].type_ref.dimensions == 1
        )
        if not is_valid:
            raise self._error("SyntaxError", ru_message("SyntaxError", "main должен иметь сигнатуру public static void main(String[] args)"), member.position.line, member.position.column, decl.name)

    def _member_chain(self, expr: Expr) -> str:
        if isinstance(expr, NameExpr):
            return expr.name
        if isinstance(expr, MemberAccessExpr):
            return f"{self._member_chain(expr.target)}.{expr.member}"
        return ""

    def _is_system_chain(self, expr: Expr) -> bool:
        return self._member_chain(expr) in {"System", "System.in", "System.out", "System.out.println"}

    def _is_zero_literal(self, expr: Expr | None) -> bool:
        return isinstance(expr, LiteralExpr) and expr.kind in {"int", "float"} and expr.value in {"0", "0.0"}

    def _type_name(self, type_ref: TypeRef) -> str:
        return type_ref.name + "[]" * type_ref.dimensions

    def _localize_semantic_detail(self, message: str) -> str:
        simple = {
            "condition must have boolean type": "условие должно иметь тип boolean",
            "void method cannot return a value": "void-метод не должен возвращать значение",
            "non-void method must return a value": "метод с возвращаемым типом должен возвращать значение",
            "method arguments are not compatible with any overload": "аргументы метода не соответствуют ни одной перегрузке",
            "indexing requires an array": "индексация возможна только у массива",
            "unsupported call target": "неподдерживаемый вызов метода",
            "finalize is not supported": "метод finalize не поддерживается",
        }
        if message in simple:
            return simple[message]
        if match := re.fullmatch(r"identifier '(.+)' is not defined", message):
            return f"идентификатор '{match.group(1)}' не объявлен"
        if match := re.fullmatch(r"method '(.+)' is not defined", message):
            return f"метод '{match.group(1)}' не объявлен"
        if match := re.fullmatch(r"method '(.+)' not found in type '(.+)'", message):
            return f"метод '{match.group(1)}' не найден в типе '{match.group(2)}'"
        if match := re.fullmatch(r"member '(.+)' not found in type '(.+)'", message):
            return f"член '{match.group(1)}' не найден в типе '{match.group(2)}'"
        if match := re.fullmatch(r"type '(.+)' is not defined", message):
            return f"тип '{match.group(1)}' не объявлен"
        if match := re.fullmatch(r"base class '(.+)' is not defined", message):
            return f"базовый класс '{match.group(1)}' не объявлен"
        if match := re.fullmatch(r"interface '(.+)' is not defined", message):
            return f"интерфейс '{match.group(1)}' не объявлен"
        if match := re.fullmatch(r"operator '(.+)' requires numeric operands", message):
            return f"оператор '{match.group(1)}' требует числовые операнды"
        if match := re.fullmatch(r"operator '(.+)' requires boolean operands", message):
            return f"оператор '{match.group(1)}' требует логические операнды"
        if match := re.fullmatch(r"operator '(.+)' requires boolean", message):
            return f"оператор '{match.group(1)}' требует логический операнд"
        if match := re.fullmatch(r"cannot assign value of type '(.+)' to '(.+)'", message):
            return f"нельзя присвоить значение типа '{match.group(1)}' переменной типа '{match.group(2)}'"
        if match := re.fullmatch(r"field '(.+)' already declared", message):
            return f"поле '{match.group(1)}' уже объявлено"
        if match := re.fullmatch(r"parameter '(.+)' already declared", message):
            return f"параметр '{match.group(1)}' уже объявлен"
        if match := re.fullmatch(r"variable '(.+)' already declared", message):
            return f"переменная '{match.group(1)}' уже объявлена"
        if match := re.fullmatch(r"type '(.+)' already declared", message):
            return f"тип '{match.group(1)}' уже объявлен"
        return message
