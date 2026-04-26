from __future__ import annotations

import subprocess
from pathlib import Path
import shutil

import pytest

from java_cpp_translator.translator import JavaToCppTranslator
from java_cpp_translator.diagnostics import TranslationError


def translate_ok(source: str, filename: str = "Main.java"):
    translator = JavaToCppTranslator()
    return translator.translate_text(source, filename)


def test_equivalence_class_40_valid_translation_contains_files():
    source = """
public interface Greeter {
    String greet(String name);
}

public class Person implements Greeter {
    String name;

    public Person(String name) {
        this.name = name;
    }

    public String greet(String other) {
        String msg = this.name + other;
        return msg;
    }
}
"""
    generated = translate_ok(source, "Person.java")
    assert "class Greeter" in generated.header_code
    assert "class Person : public Greeter" in generated.header_code
    assert "std::string name;" in generated.header_code
    assert "Person::greet" in generated.source_code


def test_equivalence_class_41_valid_control_flow_and_arrays():
    source = """
public class Counter {
    public int sum(int n) {
        int result = 0;
        for (int i = 0; i < n; i = i + 1) {
            result = result + i;
        }
        return result;
    }

    public int[] make(int n) {
        int[] arr = new int[n];
        return arr;
    }
}
"""
    generated = translate_ok(source, "Counter.java")
    assert "for (int i = 0; (i < n); (i = (i + 1)))" in generated.source_code
    assert "std::vector<int> make(int n);" in generated.header_code
    assert "std::vector<int>(n)" in generated.source_code


def test_equivalence_class_6_undefined_identifier_semantic_error():
    source = """
public class Broken {
    public int calc() {
        return x;
    }
}
"""
    translator = JavaToCppTranslator()
    with pytest.raises(TranslationError) as exc:
        translator.translate_text(source, "Broken.java")
    assert exc.value.diagnostic.code == "UndefinedIdentifier"
    assert "Broken.java" in exc.value.diagnostic.format()


def test_equivalence_class_7_duplicate_variable_error():
    source = """
public class DuplicateVar {
    public int calc() {
        int x = 1;
        int x = 2;
        return x;
    }
}
"""
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "DuplicateVar.java")
    assert exc.value.diagnostic.code == "DuplicateVariable"


def test_equivalence_class_8_type_mismatch_in_condition():
    source = """
public class Cond {
    public int calc() {
        if (1) {
            return 1;
        }
        return 0;
    }
}
"""
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "Cond.java")
    assert exc.value.diagnostic.code == "TypeMismatch"
    assert "condition must have boolean type" in exc.value.diagnostic.message


def test_equivalence_class_9_invalid_return_for_void():
    source = """
public class VoidBad {
    public void run() {
        return 1;
    }
}
"""
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "VoidBad.java")
    assert exc.value.diagnostic.code == "InvalidReturn"


def test_equivalence_class_10_not_supported_construct_lambda_like_try():
    source = """
public class Unsupported {
    public int calc() {
        try {
            return 1;
        } catch (Exception e) {
            return 0;
        }
    }
}
"""
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "Unsupported.java")
    assert exc.value.diagnostic.code in {"NotSupported", "SyntaxError"}


def test_equivalence_class_11_lexical_error_invalid_character():
    source = "public class A { public int a() { return 1 § 2; } }"
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "Lex.java")
    assert exc.value.diagnostic.code == "InvalidCharacter"


def test_equivalence_class_12_generated_cpp_compiles_with_gpp(tmp_path: Path):
    gpp = shutil.which("g++")
    if not gpp:
        pytest.skip("g++ is not installed in the environment")

    source = """
public class MathBox {
    public int twice(int x) {
        int y = x + x;
        return y;
    }
}
"""
    translator = JavaToCppTranslator()
    outputs = translator.translate_file(_write_java(tmp_path, "MathBox.java", source), tmp_path)
    main_cpp = tmp_path / "main.cpp"
    main_cpp.write_text(
        '#include "MathBox.h"\n'
        'int main() {\n'
        '    MathBox box;\n'
        '    return box.twice(2) == 4 ? 0 : 1;\n'
        '}\n',
        encoding="utf-8",
    )
    cmd = [gpp, "-std=c++17", outputs["source"], str(main_cpp), "-o", str(tmp_path / "app")]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def test_equivalence_class_13_string_and_shared_ptr_mapping():
    source = """
public class Node {
    String name;
    Node next;

    public Node(String name) {
        this.name = name;
        this.next = null;
    }

    public Node link(Node other) {
        this.next = other;
        return this.next;
    }
}
"""
    generated = translate_ok(source, "Node.java")
    assert "std::string name;" in generated.header_code
    assert "std::shared_ptr<Node> next;" in generated.header_code
    assert "nullptr" in generated.source_code


def test_report_requirements_russian_diagnostics_and_input_validation(tmp_path: Path):
    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("public class Bad {}", encoding="utf-8")

    translator = JavaToCppTranslator()
    with pytest.raises(TranslationError) as exc:
        translator.translate_file(bad_file, tmp_path)

    assert exc.value.diagnostic.code == "InvalidInputExtension"
    assert "входной файл должен иметь расширение .java" in exc.value.diagnostic.message
    assert "Ошибка" in exc.value.diagnostic.format_ru()


def test_report_requirements_console_scanner_imports_postfix_and_array_literal():
    source = """
import java.util.Scanner;

public class ConsoleApp {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int[] values = {1, 2, 3};
        int i = 0;
        i++;
        int n = sc.nextInt();
        System.out.println(n + values[0]);
        sc.close();
    }
}
"""
    generated = translate_ok(source, "ConsoleApp.java")
    assert "#include <iostream>" in generated.header_code
    assert "std::istream* sc = &std::cin;" in generated.source_code
    assert "std::vector<int> values = {1, 2, 3};" in generated.source_code
    assert "(i++);" in generated.source_code
    assert "std::cin >> value" in generated.source_code
    assert "std::cout <<" in generated.source_code


def test_report_requirements_missing_return_is_semantic_error():
    source = """
public class Missing {
    public int value() {
        int x = 1;
    }
}
"""
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "Missing.java")
    assert exc.value.diagnostic.code == "MissingReturn"
    assert "не все пути выполнения возвращают значение" in exc.value.diagnostic.message


def test_table5_case_40_division_by_zero_is_error():
    source = """
public class T {
    void m() {
        int x = 10 / 0;
    }
}
"""
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "40.java")
    assert exc.value.diagnostic.code == "DivisionByZero"
    assert "обнаружено деление на ноль" in exc.value.diagnostic.message


def test_table5_case_48_system_out_println_requires_parentheses():
    source = """
public class T {
    void m() {
        System.out.println "Hi";
    }
}
"""
    with pytest.raises(TranslationError) as exc:
        JavaToCppTranslator().translate_text(source, "48.java")
    assert exc.value.diagnostic.code == "SyntaxError"
    assert "отсутствуют круглые скобки при вызове метода" in exc.value.diagnostic.message


def _write_java(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path
