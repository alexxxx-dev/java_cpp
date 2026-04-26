from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .diagnostics import Position


@dataclass(slots=True)
class TypeRef:
    name: str
    dimensions: int = 0


@dataclass(slots=True)
class Node:
    position: Position


@dataclass(slots=True)
class CompilationUnit(Node):
    declarations: List["TypeDecl"] = field(default_factory=list)


@dataclass(slots=True)
class Parameter(Node):
    type_ref: TypeRef
    name: str


@dataclass(slots=True)
class FieldDecl(Node):
    modifiers: List[str]
    type_ref: TypeRef
    name: str
    initializer: Optional["Expr"]


@dataclass(slots=True)
class MethodDecl(Node):
    modifiers: List[str]
    return_type: TypeRef
    name: str
    parameters: List[Parameter]
    body: Optional["BlockStmt"]


@dataclass(slots=True)
class ConstructorDecl(Node):
    modifiers: List[str]
    name: str
    parameters: List[Parameter]
    body: "BlockStmt"


@dataclass(slots=True)
class InterfaceMethodDecl(Node):
    modifiers: List[str]
    return_type: TypeRef
    name: str
    parameters: List[Parameter]


@dataclass(slots=True)
class ClassDecl(Node):
    modifiers: List[str]
    name: str
    extends: Optional[str]
    implements: List[str]
    members: List[object]


@dataclass(slots=True)
class InterfaceDecl(Node):
    modifiers: List[str]
    name: str
    members: List[InterfaceMethodDecl]


TypeDecl = ClassDecl | InterfaceDecl


@dataclass(slots=True)
class Stmt(Node):
    pass


@dataclass(slots=True)
class BlockStmt(Stmt):
    statements: List[Stmt]


@dataclass(slots=True)
class VarDeclStmt(Stmt):
    type_ref: TypeRef
    name: str
    initializer: Optional["Expr"]


@dataclass(slots=True)
class ExprStmt(Stmt):
    expr: "Expr"


@dataclass(slots=True)
class IfStmt(Stmt):
    condition: "Expr"
    then_branch: Stmt
    else_branch: Optional[Stmt]


@dataclass(slots=True)
class WhileStmt(Stmt):
    condition: "Expr"
    body: Stmt


@dataclass(slots=True)
class DoWhileStmt(Stmt):
    body: Stmt
    condition: "Expr"


@dataclass(slots=True)
class ForStmt(Stmt):
    init: Optional[Stmt]
    condition: Optional["Expr"]
    update: Optional["Expr"]
    body: Stmt


@dataclass(slots=True)
class ReturnStmt(Stmt):
    expr: Optional["Expr"]


@dataclass(slots=True)
class BreakStmt(Stmt):
    pass


@dataclass(slots=True)
class ContinueStmt(Stmt):
    pass


@dataclass(slots=True)
class Expr(Node):
    inferred_type: Optional[TypeRef] = None


@dataclass(slots=True)
class LiteralExpr(Expr):
    value: str = ""
    kind: str = ""


@dataclass(slots=True)
class NameExpr(Expr):
    name: str = ""


@dataclass(slots=True)
class ThisExpr(Expr):
    pass


@dataclass(slots=True)
class UnaryExpr(Expr):
    operator: str = ""
    operand: Expr | None = None


@dataclass(slots=True)
class PostfixExpr(Expr):
    operand: Expr | None = None
    operator: str = ""


@dataclass(slots=True)
class BinaryExpr(Expr):
    left: Expr | None = None
    operator: str = ""
    right: Expr | None = None


@dataclass(slots=True)
class AssignExpr(Expr):
    target: Expr | None = None
    operator: str = "="
    value: Expr | None = None


@dataclass(slots=True)
class MemberAccessExpr(Expr):
    target: Expr | None = None
    member: str = ""


@dataclass(slots=True)
class CallExpr(Expr):
    callee: Expr | None = None
    arguments: List[Expr] = field(default_factory=list)


@dataclass(slots=True)
class NewExpr(Expr):
    type_ref: TypeRef | None = None
    arguments: List[Expr] = field(default_factory=list)
    array_size: Optional[Expr] = None


@dataclass(slots=True)
class IndexExpr(Expr):
    target: Expr | None = None
    index: Expr | None = None


@dataclass(slots=True)
class ArrayLiteralExpr(Expr):
    elements: List[Expr] = field(default_factory=list)
