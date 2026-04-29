from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .ast import *
from .diagnostics import Stage, TranslationError


@dataclass
class GeneratedFile:
    header_name: str
    header_code: str
    source_name: str
    source_code: str


class CppGenerator:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.current_class: Optional[str] = None
        self.includes: Set[str] = set()
        self.param_aliases: Dict[str, str] = {}
        self.field_names: Set[str] = set()

    def generate(self, unit: CompilationUnit, base_name: str) -> GeneratedFile:
        classes = [d for d in unit.declarations if isinstance(d, ClassDecl)]
        interfaces = [d for d in unit.declarations if isinstance(d, InterfaceDecl)]
        guard = f"{base_name.upper()}_H"
        header_lines: List[str] = [f"#ifndef {guard}", f"#define {guard}"]
        self.includes = set()
        decl_lines: List[str] = []
        source_lines: List[str] = []

        for interface in interfaces:
            decl_lines.extend(self._emit_interface_decl(interface))
            decl_lines.append("")
        for cls in classes:
            decl_lines.extend(self._emit_class_decl(cls))
            decl_lines.append("")
            source_lines.extend(self._emit_class_defs(cls))
            source_lines.append("")

        include_block = self._emit_includes()
        header_lines.extend(include_block)
        if include_block:
            header_lines.append("")
        header_lines.extend(decl_lines)
        header_lines.append("#endif")

        source_header = [f'#include "{base_name}.h"']
        source_includes = []
        if "memory" in self.includes:
            source_includes.append("#include <memory>")
        if "vector" in self.includes:
            source_includes.append("#include <vector>")
        if "string" in self.includes:
            source_includes.append("#include <string>")
        if "cstdint" in self.includes:
            source_includes.append("#include <cstdint>")
        if "iostream" in self.includes or "header_iostream" in self.includes:
            source_includes.append("#include <iostream>")
        if source_includes:
            source_header.extend(source_includes)
        if source_lines:
            source_header.append("")
        source_header.extend(source_lines)
        return GeneratedFile(f"{base_name}.h", "\n".join(header_lines).rstrip() + "\n", f"{base_name}.cpp", "\n".join(source_header).rstrip() + "\n")

    def _emit_includes(self) -> List[str]:
        includes = []
        if "string" in self.includes:
            includes.append("#include <string>")
        if "memory" in self.includes:
            includes.append("#include <memory>")
        if "vector" in self.includes:
            includes.append("#include <vector>")
        if "cstdint" in self.includes:
            includes.append("#include <cstdint>")
        if "header_iostream" in self.includes:
            includes.append("#include <iostream>")
        return includes

    def _emit_interface_decl(self, decl: InterfaceDecl) -> List[str]:
        lines = [f"class {decl.name}", "{", "public:", f"    virtual ~{decl.name}() = default;"]
        for member in decl.members:
            params = ", ".join(f"{self._cpp_type(p.type_ref)} {p.name}" for p in member.parameters)
            lines.append(f"    virtual {self._cpp_type(member.return_type)} {member.name}({params}) = 0;")
        lines.append("};")
        return lines

    def _emit_class_decl(self, decl: ClassDecl) -> List[str]:
        self.current_class = decl.name
        bases: List[str] = []
        if decl.extends:
            bases.append(f"public {decl.extends}")
        for interface in decl.implements:
            bases.append(f"public {interface}")
        head = f"class {decl.name}" + (" : " + ", ".join(bases) if bases else "")
        lines = [head, "{", "public:"]
        for member in decl.members:
            if isinstance(member, FieldDecl):
                lines.append(f"    {self._cpp_type(member.type_ref)} {member.name};")
            elif isinstance(member, ConstructorDecl):
                params = ", ".join(f"{self._cpp_type(p.type_ref)} {self._cpp_param_name(p, decl)}" for p in member.parameters)
                lines.append(f"    {decl.name}({params});")
            elif isinstance(member, MethodDecl):
                params = ", ".join(f"{self._cpp_type(p.type_ref)} {p.name}" for p in member.parameters)
                prefix = "static " if "static" in member.modifiers else ""
                lines.append(f"    {prefix}{self._cpp_type(member.return_type)} {member.name}({params});")
        lines.append("};")
        return lines

    def _emit_class_defs(self, decl: ClassDecl) -> List[str]:
        self.current_class = decl.name
        self.field_names = {member.name for member in decl.members if isinstance(member, FieldDecl)}
        lines: List[str] = []
        for member in decl.members:
            if isinstance(member, ConstructorDecl):
                self.param_aliases = {p.name: self._cpp_param_name(p, decl) for p in member.parameters}
                params = ", ".join(f"{self._cpp_type(p.type_ref)} {self.param_aliases[p.name]}" for p in member.parameters)
                lines.append(f"{decl.name}::{decl.name}({params})")
                lines.extend(self._emit_block(member.body))
                lines.append("")
                self.param_aliases = {}
            elif isinstance(member, MethodDecl):
                if member.body is None:
                    continue
                self.param_aliases = {}
                params = ", ".join(f"{self._cpp_type(p.type_ref)} {p.name}" for p in member.parameters)
                lines.append(f"{self._cpp_type(member.return_type)} {decl.name}::{member.name}({params})")
                lines.extend(self._emit_block(member.body))
                lines.append("")
        return lines

    def _emit_block(self, block: BlockStmt, indent: int = 0) -> List[str]:
        pad = " " * indent
        lines = [pad + "{"]
        for stmt in block.statements:
            lines.extend(self._emit_stmt(stmt, indent + 4))
        lines.append(pad + "}")
        return lines

    def _emit_stmt(self, stmt: Stmt, indent: int) -> List[str]:
        pad = " " * indent
        if isinstance(stmt, BlockStmt):
            return self._emit_block(stmt, indent)
        if isinstance(stmt, VarDeclStmt):
            if isinstance(stmt.initializer, NewExpr) and stmt.initializer.array_size is not None:
                return [f"{pad}{self._cpp_type(stmt.type_ref)} {stmt.name}({self._emit_expr(stmt.initializer.array_size)});"]
            init = f" = {self._emit_expr(stmt.initializer)}" if stmt.initializer else ""
            return [f"{pad}{self._cpp_type(stmt.type_ref)} {stmt.name}{init};"]
        if isinstance(stmt, ExprStmt):
            expr = self._emit_expr(stmt.expr)
            if isinstance(stmt.expr, AssignExpr) and expr.startswith("(") and expr.endswith(")"):
                expr = expr[1:-1]
            return [f"{pad}{expr};"]
        if isinstance(stmt, IfStmt):
            lines = [f"{pad}if ({self._emit_expr(stmt.condition)})"]
            lines.extend(self._emit_stmt(stmt.then_branch, indent))
            if stmt.else_branch:
                lines.append(f"{pad}else")
                lines.extend(self._emit_stmt(stmt.else_branch, indent))
            return lines
        if isinstance(stmt, WhileStmt):
            lines = [f"{pad}while ({self._emit_expr(stmt.condition)})"]
            lines.extend(self._emit_stmt(stmt.body, indent))
            return lines
        if isinstance(stmt, DoWhileStmt):
            lines = [f"{pad}do"]
            lines.extend(self._emit_stmt(stmt.body, indent))
            lines.append(f"{pad}while ({self._emit_expr(stmt.condition)});")
            return lines
        if isinstance(stmt, ForStmt):
            init = ""
            if isinstance(stmt.init, VarDeclStmt):
                init = f"{self._cpp_type(stmt.init.type_ref)} {stmt.init.name}"
                if stmt.init.initializer:
                    init += f" = {self._emit_expr(stmt.init.initializer)}"
            elif isinstance(stmt.init, ExprStmt):
                init = self._emit_expr(stmt.init.expr)
            cond = self._emit_expr(stmt.condition) if stmt.condition else ""
            update = self._emit_expr(stmt.update) if stmt.update else ""
            lines = [f"{pad}for ({init}; {cond}; {update})"]
            lines.extend(self._emit_stmt(stmt.body, indent))
            return lines
        if isinstance(stmt, ReturnStmt):
            return [f"{pad}return {self._emit_expr(stmt.expr)};" if stmt.expr else f"{pad}return;"]
        if isinstance(stmt, BreakStmt):
            return [f"{pad}break;"]
        if isinstance(stmt, ContinueStmt):
            return [f"{pad}continue;"]
        raise TranslationError(Stage.GEN, "NotSupported", f"statement '{type(stmt).__name__}' is not supported", self.filename, stmt.position.line, stmt.position.column)

    def _emit_expr(self, expr: Optional[Expr]) -> str:
        if expr is None:
            return ""
        if isinstance(expr, LiteralExpr):
            if expr.kind == "null":
                self.includes.add("memory")
                return "nullptr"
            return expr.value
        if isinstance(expr, NameExpr):
            if expr.name in self.field_names and expr.name not in self.param_aliases:
                return f"this->{expr.name}"
            return self.param_aliases.get(expr.name, expr.name)
        if isinstance(expr, ThisExpr):
            return "this"
        if isinstance(expr, UnaryExpr):
            return f"({expr.operator}{self._emit_expr(expr.operand)})"
        if isinstance(expr, PostfixExpr):
            return f"({self._emit_expr(expr.operand)}{expr.operator})"
        if isinstance(expr, BinaryExpr):
            if expr.operator == "+" and ((expr.left and expr.left.inferred_type and expr.left.inferred_type.name == "String") or (expr.right and expr.right.inferred_type and expr.right.inferred_type.name == "String")):
                self.includes.add("string")
            return f"({self._emit_expr(expr.left)} {expr.operator} {self._emit_expr(expr.right)})"
        if isinstance(expr, AssignExpr):
            return f"({self._emit_expr(expr.target)} {expr.operator} {self._emit_expr(expr.value)})"
        if isinstance(expr, MemberAccessExpr):
            chain = self._member_chain(expr)
            if chain in {"System.in", "System.out", "System.out.println"}:
                return chain
            arrow = "->" if expr.target and expr.target.inferred_type and self._is_reference(expr.target.inferred_type) else "."
            return f"{self._emit_expr(expr.target)}{arrow}{expr.member}"
        if isinstance(expr, CallExpr):
            if isinstance(expr.callee, MemberAccessExpr):
                chain = self._member_chain(expr.callee)
                if chain == "System.out.println":
                    self.includes.add("iostream")
                    if not expr.arguments:
                        return "std::cout"
                    args = " << ".join(self._emit_expr(arg) for arg in expr.arguments)
                    return f"std::cout << {args}"
                if expr.callee.member in {"nextInt", "nextLine", "nextDouble"}:
                    self.includes.add("iostream")
                    if expr.callee.member == "nextLine":
                        self.includes.add("string")
                        return "([&](){ std::string value; std::getline(std::cin, value); return value; }())"
                    ctype = "int" if expr.callee.member == "nextInt" else "double"
                    return f"([&](){{ {ctype} value; std::cin >> value; return value; }}())"
                if expr.callee.member == "close":
                    return "static_cast<void>(0)"
            callee = self._emit_expr(expr.callee)
            args = ", ".join(self._emit_expr(arg) for arg in expr.arguments)
            return f"{callee}({args})"
        if isinstance(expr, NewExpr):
            if expr.type_ref.name == "Scanner":
                self.includes.add("iostream")
                return "&std::cin"
            if expr.array_size is not None:
                self.includes.add("vector")
                inner = self._cpp_type(TypeRef(expr.type_ref.name, max(expr.type_ref.dimensions - 1, 0)))
                return f"std::vector<{inner}>({self._emit_expr(expr.array_size)})"
            if self._is_reference(expr.type_ref):
                self.includes.add("memory")
                args = ", ".join(self._emit_expr(arg) for arg in expr.arguments)
                return f"std::make_shared<{expr.type_ref.name}>({args})"
            raise TranslationError(Stage.GEN, "NotSupported", "new for primitive types is not supported", self.filename, expr.position.line, expr.position.column)
        if isinstance(expr, IndexExpr):
            return f"{self._emit_expr(expr.target)}[{self._emit_expr(expr.index)}]"
        if isinstance(expr, ArrayLiteralExpr):
            return "{" + ", ".join(self._emit_expr(element) for element in expr.elements) + "}"
        raise TranslationError(Stage.GEN, "NotSupported", f"expression '{type(expr).__name__}' is not supported", self.filename, expr.position.line, expr.position.column)

    def _cpp_type(self, type_ref: TypeRef) -> str:
        if type_ref.dimensions > 0:
            self.includes.add("vector")
            inner = self._cpp_type(TypeRef(type_ref.name, type_ref.dimensions - 1))
            return f"std::vector<{inner}>"
        mapping = {
            "int": "int",
            "long": "long long",
            "short": "short",
            "byte": "std::int8_t",
            "float": "float",
            "double": "double",
            "boolean": "bool",
            "char": "char",
            "void": "void",
            "String": "std::string",
        }
        if type_ref.name == "String":
            self.includes.add("string")
            return "std::string"
        if type_ref.name == "byte":
            self.includes.add("cstdint")
            return "std::int8_t"
        if type_ref.name == "Scanner":
            self.includes.add("iostream")
            self.includes.add("header_iostream")
            return "std::istream*"
        if type_ref.name in mapping:
            return mapping[type_ref.name]
        if self._is_reference(type_ref):
            self.includes.add("memory")
            return f"std::shared_ptr<{type_ref.name}>"
        return type_ref.name

    def _is_reference(self, type_ref: TypeRef) -> bool:
        return type_ref.name not in {"int", "long", "short", "byte", "float", "double", "boolean", "char", "void", "Scanner"} and type_ref.dimensions == 0

    def _member_chain(self, expr: Expr) -> str:
        if isinstance(expr, NameExpr):
            return expr.name
        if isinstance(expr, MemberAccessExpr):
            return f"{self._member_chain(expr.target)}.{expr.member}"
        return ""

    def _cpp_param_name(self, parameter: Parameter, decl: ClassDecl) -> str:
        field_names = {member.name for member in decl.members if isinstance(member, FieldDecl)}
        if parameter.name in field_names:
            return f"{parameter.name}_"
        return parameter.name
