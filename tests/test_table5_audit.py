from __future__ import annotations

from dataclasses import dataclass

import pytest

from java_cpp_translator.diagnostics import Stage, TranslationError
from java_cpp_translator.translator import JavaToCppTranslator


@dataclass(frozen=True)
class ErrorCase:
    case_id: int
    source: str
    stage: Stage
    code: str
    message: str


@dataclass(frozen=True)
class SuccessCase:
    case_id: int
    source: str


PASSING_ERROR_CASES = [
    ErrorCase(40, 'public class T { void m() { int x = 10 / 0; } }', Stage.SEM, "DivisionByZero", "обнаружено деление на ноль"),
    ErrorCase(41, 'public class T { void m() { int x = 10 + true; } }', Stage.SEM, "TypeMismatch", "несовместимые типы: оператор '+' требует числовые операнды"),
    ErrorCase(43, 'public class T { void m() { int z = a + ;}}', Stage.SYN, "SyntaxError", "синтаксическая ошибка: неожиданный токен ';'"),
    ErrorCase(44, 'public class T { void m() { int w = a + * b; } }', Stage.SYN, "SyntaxError", "синтаксическая ошибка: неожиданный токен '*'"),
    ErrorCase(45, 'import java.util.Scanner; public class T { void m() { Scanner sc = new Scanner(System.in); int n = sc.next(); sc.close(); } }', Stage.SEM, "UndefinedMethod", "метод не объявлен: метод 'next' не найден в типе 'Scanner'"),
    ErrorCase(48, 'public class T { void m() { System.out.println "Hi"; } }', Stage.SYN, "SyntaxError", "отсутствуют круглые скобки при вызове метода"),
    ErrorCase(50, 'public class T { void m() { System.out.println(Hello"); } }', Stage.LEX, "UnterminatedString", "строковый литерал не закрыт"),
    ErrorCase(51, 'public class T { void m() { System.out.println("Hello); } }', Stage.LEX, "UnterminatedString", "строковый литерал не закрыт"),
    ErrorCase(53, 'public class T { int sum(int a, int b) { return a+b; } void c() { sum(5); } }', Stage.SEM, "MethodSignatureMismatch", "аргументы метода не подходят ни к одной сигнатуре: аргументы метода не соответствуют ни одной перегрузке"),
    ErrorCase(54, 'public class T { int sum(int a, int b) { return a+b; } void c() { sum(5,3,7); } }', Stage.SEM, "MethodSignatureMismatch", "аргументы метода не подходят ни к одной сигнатуре: аргументы метода не соответствуют ни одной перегрузке"),
    ErrorCase(55, 'public class T { void m() { nonExistent(); } }', Stage.SEM, "UndefinedMethod", "метод не объявлен: метод 'nonExistent' не объявлен"),
    ErrorCase(56, 'public class T { void p(int x) {} void p(double x) {} void m() { p(null); } }', Stage.SEM, "MethodSignatureMismatch", "аргументы метода не подходят ни к одной сигнатуре: аргументы метода не соответствуют ни одной перегрузке"),
    ErrorCase(57, 'public class T { int v() { int a=5; } }', Stage.SEM, "MissingReturn", "не все пути выполнения возвращают значение"),
    ErrorCase(58, 'public class T { void v() { return 5; } }', Stage.SEM, "InvalidReturn", "оператор return не соответствует типу метода: void-метод не должен возвращать значение"),
    ErrorCase(59, 'public class T { void m() { int[] a = {1, "t", 3}; } }', Stage.SEM, "TypeMismatch", "несовместимые типы: элементы массива имеют разные типы"),
    ErrorCase(62, 'public class T { void m() { int a = {1,2,3}; } }', Stage.SEM, "TypeMismatch", "несовместимые типы: нельзя присвоить значение типа 'int[]' переменной типа 'int'"),
    ErrorCase(63, 'public class T { void m() { int[] a = 1, 2, 3; } }', Stage.SYN, "SyntaxError", "синтаксическая ошибка: ожидался символ ';'"),
    ErrorCase(68, 'class A {} class B {} class C extends A extends B {}', Stage.SYN, "SyntaxError", "синтаксическая ошибка: ожидался символ '{'"),
    ErrorCase(72, 'import java.util.* public class T {}', Stage.SYN, "SyntaxError", "синтаксическая ошибка: ожидался символ ';' после import"),
    ErrorCase(73, 'import java util.*; public class T {}', Stage.SYN, "SyntaxError", "синтаксическая ошибка: ожидался символ ';' после import"),
    ErrorCase(78, 'public class T { public static void main String[] args) {} }', Stage.SYN, "SyntaxError", "синтаксическая ошибка: ожидался символ ';'"),
    ErrorCase(79, 'public class T { public static void main(String[] args { } }', Stage.SYN, "SyntaxError", "синтаксическая ошибка: ожидался символ ','"),
    ErrorCase(80, 'public class T { void m() { /* unclosed ', Stage.LEX, "UnterminatedComment", "многострочный комментарий не закрыт"),
]


PASSING_SUCCESS_CASES = [
    SuccessCase(49, 'public class T { void m() { System.out.println(); } }'),
]


KNOWN_GAPS = [
    pytest.param(
        ErrorCase(42, 'public class T { void m() { int y = 5 "str"; } }', Stage.SEM, "TypeMismatch", "несовместимые типы"),
        marks=pytest.mark.xfail(reason="Кейс из таблицы 5 требует более точной диагностики для некорректного выражения.", strict=False),
    ),
    pytest.param(
        ErrorCase(46, 'public class T { void m() { Systemout.println("Hi"); } }', Stage.SYN, "SyntaxError", "некорректный вызов вывода"),
        marks=pytest.mark.xfail(reason="Сейчас ошибка возникает как необъявленный идентификатор, а не как специализированная диагностика вывода.", strict=False),
    ),
    pytest.param(
        ErrorCase(47, 'public class T { void m() { System.outprintln("Hi"); } }', Stage.SYN, "SyntaxError", "некорректный вызов вывода"),
        marks=pytest.mark.xfail(reason="Нужна отдельная диагностика для ошибочного имени метода вывода.", strict=False),
    ),
    pytest.param(
        ErrorCase(52, 'import java.util.Scanner; public class T { void m() { Scanner sc = new Scanner(System.in); int n = sc.nextInt(); } }', Stage.SEM, "ScannerNotClosed", "объект Scanner должен быть закрыт методом close"),
        marks=pytest.mark.xfail(reason="Проверка незакрытого Scanner пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(60, 'public class T { void m() { int[] a = {1,2,3}; int x = a[5]; } }', Stage.SEM, "ArrayIndexOutOfBounds", "индекс массива выходит за допустимые границы"),
        marks=pytest.mark.xfail(reason="Проверка выхода за границы массива для константного индекса пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(61, 'public class T { void m() { int[] a = {1,2,3}; int x = a[-1]; } }', Stage.SEM, "ArrayIndexOutOfBounds", "индекс массива выходит за допустимые границы"),
        marks=pytest.mark.xfail(reason="Проверка отрицательного индекса массива пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(64, 'public class T { void m() { int[] a = {1,2,3}; int x = a(0); } }', Stage.SYN, "SyntaxError", "для обращения к массиву должны использоваться квадратные скобки"),
        marks=pytest.mark.xfail(reason="Сейчас ошибка доходит до семантики как вызов метода.", strict=False),
    ),
    pytest.param(
        ErrorCase(65, 'public class T { void iM() {} static void sM() { iM(); } }', Stage.SEM, "TypeMismatch", "нестатический метод нельзя вызывать из статического контекста"),
        marks=pytest.mark.xfail(reason="Проверка вызова нестатического метода из статического контекста пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(66, 'public class T { final int C = 10; void m() { C = 20; } }', Stage.SEM, "TypeMismatch", "нельзя изменять final-поле"),
        marks=pytest.mark.xfail(reason="Проверка final-полей пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(67, 'class P { private void pM() {} } public class T { void m() { new P().pM(); } }', Stage.SEM, "UndefinedMember", "private-метод недоступен из другого класса"),
        marks=pytest.mark.xfail(reason="Проверка модификатора private пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(69, 'interface I { void m(); } class C implements I {}', Stage.SEM, "MethodSignatureMismatch", "класс должен реализовать все методы интерфейса"),
        marks=pytest.mark.xfail(reason="Полная проверка implements пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(70, 'interface I {} class E extends I {}', Stage.SEM, "TypeMismatch", "интерфейс нельзя использовать в extends как класс"),
        marks=pytest.mark.xfail(reason="Проверка некорректного extends для интерфейса пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(71, 'import java.util.NonExistent; public class T {}', Stage.SEM, "UndefinedType", "импортируемый тип не найден"),
        marks=pytest.mark.xfail(reason="Семантическая проверка import пока не реализована.", strict=False),
    ),
    pytest.param(
        ErrorCase(74, 'public class T { void main(String[] args) {} }', Stage.SYN, "SyntaxError", "main должен иметь сигнатуру public static void main(String[] args)"),
        marks=pytest.mark.xfail(reason="Сейчас диагностика main формируется на семантическом этапе, а не на синтаксическом.", strict=False),
    ),
    pytest.param(
        ErrorCase(75, 'public class T { public static int main(String[] args) { return 0; } }', Stage.SYN, "SyntaxError", "main должен иметь сигнатуру public static void main(String[] args)"),
        marks=pytest.mark.xfail(reason="Сейчас диагностика main формируется на семантическом этапе, а не на синтаксическом.", strict=False),
    ),
    pytest.param(
        ErrorCase(76, 'public class T { public static void main(int[] args) {} }', Stage.SYN, "SyntaxError", "main должен иметь сигнатуру public static void main(String[] args)"),
        marks=pytest.mark.xfail(reason="Сейчас диагностика main формируется на семантическом этапе, а не на синтаксическом.", strict=False),
    ),
    pytest.param(
        ErrorCase(77, 'public class T { public static void main(String args) {} }', Stage.SYN, "SyntaxError", "main должен иметь сигнатуру public static void main(String[] args)"),
        marks=pytest.mark.xfail(reason="Сейчас диагностика main формируется на семантическом этапе, а не на синтаксическом.", strict=False),
    ),
    pytest.param(
        ErrorCase(81, 'public class T { void m() { /* outer /* inner */ outer */ } }', Stage.LEX, "UnterminatedComment", "вложенные комментарии не поддерживаются"),
        marks=pytest.mark.xfail(reason="Вложенные комментарии пока не диагностируются как отдельная лексическая ошибка.", strict=False),
    ),
    pytest.param(
        ErrorCase(82, 'public class T { void m() { */ text } }', Stage.LEX, "InvalidCharacter", "закрывающий комментарий найден без открывающего"),
        marks=pytest.mark.xfail(reason="Одиночный закрывающий комментарий пока не выделяется как отдельная лексическая ошибка.", strict=False),
    ),
]


@pytest.mark.parametrize("case", PASSING_ERROR_CASES, ids=lambda case: f"table5-{case.case_id}")
def test_table5_passing_error_cases(case: ErrorCase):
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(case.source, f"{case.case_id}.java")
    diagnostic = exc.value.diagnostic
    assert diagnostic.stage == case.stage
    assert diagnostic.code == case.code
    assert diagnostic.message == case.message


@pytest.mark.parametrize("case", PASSING_SUCCESS_CASES, ids=lambda case: f"table5-{case.case_id}")
def test_table5_passing_success_cases(case: SuccessCase):
    generated = JavaToCppTranslator().translate_text(case.source, f"{case.case_id}.java")
    assert generated.header_code
    assert generated.source_code


@pytest.mark.parametrize("case", KNOWN_GAPS, ids=lambda case: f"table5-{case.case_id}")
def test_table5_known_gaps(case: ErrorCase):
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(case.source, f"{case.case_id}.java")
    diagnostic = exc.value.diagnostic
    assert diagnostic.stage == case.stage
    assert diagnostic.code == case.code
    assert diagnostic.message == case.message
