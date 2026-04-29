from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .translator import JavaToCppTranslator


class TranslatorGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Транслятор Java в C++")
        self.root.geometry("900x640")
        self.file_path_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value="out")
        self.status_var = tk.StringVar(value="Выберите Java-файл и каталог вывода.")
        self._build()

    def _build(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(3, weight=1)
        main.rowconfigure(5, weight=1)

        ttk.Label(main, text="Java-файл").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(main, textvariable=self.file_path_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(main, text="Выбрать...", command=self._pick_file).grid(row=0, column=2, padx=(8, 0), pady=(0, 8))

        ttk.Label(main, text="Каталог вывода").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(main, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(main, text="Выбрать...", command=self._pick_output_dir).grid(row=1, column=2, padx=(8, 0), pady=(0, 8))

        ttk.Button(main, text="Перевести в C++", command=self._translate).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(main, text="Исходный код").grid(row=3, column=0, columnspan=3, sticky="w")
        self.source_text = tk.Text(main, wrap="word", height=12)
        self.source_text.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(4, 12))

        ttk.Label(main, text="Диагностика и результат").grid(row=5, column=0, columnspan=3, sticky="w")
        self.log_text = tk.Text(main, wrap="word", height=10)
        self.log_text.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(4, 8))
        self._add_copy_bindings(self.log_text)

        status = ttk.Label(main, textvariable=self.status_var, anchor="w")
        status.grid(row=7, column=0, columnspan=3, sticky="ew")

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите Java-файл",
            filetypes=[("Java-файлы", "*.java"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        self.file_path_var.set(path)
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Ошибка чтения", str(exc))
            return
        self.source_text.delete("1.0", tk.END)
        self.source_text.insert("1.0", content)
        self.status_var.set("Java-файл загружен.")

    def _pick_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Выберите каталог вывода")
        if path:
            self.output_dir_var.set(path)

    def _translate(self) -> None:
        file_path = Path(self.file_path_var.get().strip())
        output_dir = self.output_dir_var.get().strip()
        self.log_text.delete("1.0", tk.END)

        if not file_path:
            messagebox.showwarning("Нет файла", "Сначала выберите Java-файл.")
            return
        if not file_path.exists():
            messagebox.showerror("Файл не найден", f"Файл не существует: {file_path}")
            return
        if not output_dir:
            messagebox.showwarning("Нет каталога", "Выберите каталог вывода.")
            return

        translator = JavaToCppTranslator()
        summary = translator.translate_many([file_path], output_dir)
        if translator.diagnostics.items:
            self.log_text.insert(
                "1.0",
                "\n".join(diagnostic.format_ru() for diagnostic in translator.diagnostics.items),
            )
        else:
            outputs = summary["outputs"][0]
            self.log_text.insert(
                "1.0",
                "Трансляция успешно завершена.\n"
                f"Заголовочный файл: {outputs['header']}\n"
                f"Файл реализации: {outputs['source']}",
            )

        if summary["errors"] == 0:
            self.status_var.set("Трансляция завершена.")
        else:
            self.status_var.set("Трансляция завершена с ошибками.")

    def _add_copy_bindings(self, widget: tk.Text) -> None:
        menu = tk.Menu(widget, tearoff=False)
        menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Выделить всё", command=lambda: self._select_all(widget))
        widget.bind("<Control-a>", lambda event: self._select_all(widget))
        widget.bind("<Button-3>", lambda event: self._show_context_menu(menu, event))

    def _select_all(self, widget: tk.Text) -> str:
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "1.0")
        widget.see("insert")
        return "break"

    def _show_context_menu(self, menu: tk.Menu, event: tk.Event) -> str:
        menu.tk_popup(event.x_root, event.y_root)
        return "break"


def main() -> None:
    root = tk.Tk()
    ttk.Style(root).theme_use("clam")
    TranslatorGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
