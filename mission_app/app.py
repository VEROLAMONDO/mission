"""Tkinter Windows desktop application for local Mission TodoList usage."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from .ai import AIClient, AIConfig
from .models import TaskStatus, TaskType, next_review_at, reward_tokens
from .storage import MissionStore


class MissionApp(tk.Tk):
    def __init__(self, store: MissionStore | None = None) -> None:
        super().__init__()
        self.title("Mission TodoList - Windows 本地端")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.store = store or MissionStore()
        self._build_styles()
        self._build_layout()
        self.refresh_all()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Metric.TLabel", font=("Microsoft YaHei UI", 11, "bold"), padding=8)
        style.configure("Treeview", rowheight=28)

    def _build_layout(self) -> None:
        header = ttk.Frame(self, padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Mission TodoList", style="Title.TLabel").pack(side="left")
        self.balance_label = ttk.Label(header, text="代币：0", style="Metric.TLabel")
        self.balance_label.pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._build_today_tab()
        self._build_projects_tab()
        self._build_cards_tab()
        self._build_notes_tab()
        self._build_settings_tab()

    def _build_today_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="今日任务")
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="新增20分钟任务", command=self.add_minimum_task).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="确认完成", command=self.complete_selected_task).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="刷新", command=self.refresh_all).pack(side="left")
        self.today_tree = ttk.Treeview(
            tab,
            columns=("id", "type", "progress", "estimated", "difficulty", "status", "deadline"),
            show="headings",
        )
        for col, text, width in [
            ("id", "ID", 60),
            ("type", "类型", 90),
            ("progress", "进度", 80),
            ("estimated", "预计分钟", 90),
            ("difficulty", "难度", 70),
            ("status", "状态", 120),
            ("deadline", "截止", 130),
        ]:
            self.today_tree.heading(col, text=text)
            self.today_tree.column(col, width=width, anchor="center")
        self.today_tree.heading("#0", text="任务")
        self.today_tree.pack(fill="both", expand=True)
        self.today_tree.bind("<Double-1>", lambda _event: self.complete_selected_task())

    def _build_projects_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="项目任务树")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        toolbar = ttk.Frame(left)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="AI/本地拆分项目", command=self.generate_project).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="新增子任务", command=self.add_child_task).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="重算进度", command=self.recalculate_selected_project).pack(side="left")
        self.project_tree = ttk.Treeview(
            left,
            columns=("id", "progress", "estimated", "difficulty", "status"),
            show="tree headings",
        )
        self.project_tree.heading("#0", text="任务树")
        self.project_tree.column("#0", width=440)
        for col, text, width in [
            ("id", "ID", 60),
            ("progress", "进度", 80),
            ("estimated", "预计分钟", 90),
            ("difficulty", "难度", 70),
            ("status", "状态", 110),
        ]:
            self.project_tree.heading(col, text=text)
            self.project_tree.column(col, width=width, anchor="center")
        self.project_tree.pack(fill="both", expand=True)

        right = ttk.LabelFrame(tab, text="项目说明", padding=10)
        right.pack(side="right", fill="y", padx=(12, 0))
        ttk.Label(
            right,
            text="规则：项目进度由子任务自动加权计算；\n最小任务推荐20分钟，由用户确认完成。",
            justify="left",
        ).pack(anchor="w")

    def _build_cards_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="Anki记忆卡片")
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="新增卡片", command=self.add_card).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="答对", command=lambda: self.review_card("correct")).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="答错", command=lambda: self.review_card("wrong")).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="导入CSV", command=self.import_cards_csv).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="导出CSV", command=self.export_cards_csv).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="导入APKG", command=self.import_cards_apkg).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="导出APKG", command=self.export_cards_apkg).pack(side="left")
        self.card_tree = ttk.Treeview(
            tab,
            columns=("id", "deck", "front", "back", "review", "wrong", "next", "status"),
            show="headings",
        )
        for col, text, width in [
            ("id", "ID", 55),
            ("deck", "牌组", 120),
            ("front", "正面", 220),
            ("back", "背面", 220),
            ("review", "复习", 70),
            ("wrong", "错误", 70),
            ("next", "下次复习", 170),
            ("status", "状态", 100),
        ]:
            self.card_tree.heading(col, text=text)
            self.card_tree.column(col, width=width, anchor="center" if col in {"id", "review", "wrong", "status"} else "w")
        self.card_tree.pack(fill="both", expand=True)

    def _build_notes_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="Markdown杂记/日志")
        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="保存杂记", command=self.save_note).pack(side="left", padx=(0, 6))
        ttk.Button(top, text="导出备份JSON", command=self.export_backup).pack(side="left")
        self.note_title = ttk.Entry(top)
        self.note_title.insert(0, "今日杂记")
        self.note_title.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.note_text = tk.Text(tab, wrap="word", font=("Consolas", 11))
        self.note_text.pack(fill="both", expand=True)
        self.note_text.insert("1.0", "# 今日记录\n\n- 完成：\n- 问题：\n- 明日改进：\n")

    def _build_settings_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(tab, text="AI接口设置")
        self.ai_enabled = tk.BooleanVar(value=False)
        self.ai_base_url = tk.StringVar(value="")
        self.ai_key = tk.StringVar(value="")
        self.ai_model = tk.StringVar(value="local-model")
        ttk.Checkbutton(tab, text="启用AI接口（OpenAI兼容 / 本地大模型均可）", variable=self.ai_enabled).grid(row=0, column=0, columnspan=2, sticky="w", pady=6)
        for row, (label, variable) in enumerate(
            [("API Base URL", self.ai_base_url), ("API Key", self.ai_key), ("Model", self.ai_model)], start=1
        ):
            ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(tab, textvariable=variable, width=70, show="*" if label == "API Key" else "").grid(row=row, column=1, sticky="ew", pady=6)
        tab.columnconfigure(1, weight=1)
        ttk.Label(
            tab,
            text="AI不可用时会自动回退到本地规则拆分；任务草稿需用户确认后才写入。",
            foreground="#555",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))

    def refresh_all(self) -> None:
        self.balance_label.config(text=f"代币：{self.store.token_balance()}")
        self.refresh_today()
        self.refresh_projects()
        self.refresh_cards()

    def refresh_today(self) -> None:
        self.today_tree.delete(*self.today_tree.get_children())
        rows = self.store.rows(
            "SELECT * FROM tasks WHERE status != ? ORDER BY deadline IS NULL, deadline, id DESC LIMIT 200",
            (TaskStatus.COMPLETED,),
        )
        for row in rows:
            self.today_tree.insert(
                "",
                "end",
                iid=f"task-{row['id']}",
                text=row["title"],
                values=(row["id"], row["type"], f"{row['progress']:.0f}%", row["estimated_minutes"], row["difficulty"], row["status"], row["deadline"] or ""),
            )

    def refresh_projects(self) -> None:
        self.project_tree.delete(*self.project_tree.get_children())
        rows = self.store.rows("SELECT * FROM tasks ORDER BY parent_id IS NOT NULL, parent_id, id")
        by_parent: dict[int | None, list[Any]] = {}
        for row in rows:
            by_parent.setdefault(row["parent_id"], []).append(row)

        def add_nodes(parent_db_id: int | None, parent_item: str = "") -> None:
            for row in by_parent.get(parent_db_id, []):
                item = self.project_tree.insert(
                    parent_item,
                    "end",
                    iid=f"project-{row['id']}",
                    text=row["title"],
                    values=(row["id"], f"{row['progress']:.0f}%", row["estimated_minutes"], row["difficulty"], row["status"]),
                    open=True,
                )
                add_nodes(int(row["id"]), item)

        add_nodes(None)

    def refresh_cards(self) -> None:
        self.card_tree.delete(*self.card_tree.get_children())
        rows = self.store.rows(
            """
            SELECT memory_cards.*, decks.name AS deck_name
            FROM memory_cards JOIN decks ON memory_cards.deck_id = decks.id
            ORDER BY next_review_at IS NULL, next_review_at, memory_cards.id DESC
            """
        )
        for row in rows:
            self.card_tree.insert(
                "",
                "end",
                iid=f"card-{row['id']}",
                values=(row["id"], row["deck_name"], row["front"], row["back"], row["review_count"], row["wrong_count"], row["next_review_at"] or "", row["status"]),
            )

    def _selected_task_id(self, tree: ttk.Treeview) -> int | None:
        selection = tree.selection()
        if not selection:
            return None
        return int(tree.item(selection[0], "values")[0])

    def add_minimum_task(self) -> None:
        title = simpledialog.askstring("新增20分钟任务", "任务标题：", parent=self)
        if not title:
            return
        self.store.create_task(title=title, task_type=TaskType.MINIMUM, estimated_minutes=20)
        self.refresh_all()

    def add_child_task(self) -> None:
        parent_id = self._selected_task_id(self.project_tree)
        if not parent_id:
            messagebox.showinfo("提示", "请先在项目任务树中选择父任务。")
            return
        title = simpledialog.askstring("新增子任务", "子任务标题：", parent=self)
        if not title:
            return
        minutes = simpledialog.askinteger("预计分钟", "预计分钟：", initialvalue=20, minvalue=1, parent=self) or 20
        task_type = TaskType.MINIMUM if minutes <= 20 else TaskType.PROJECT
        self.store.create_task(title=title, parent_id=parent_id, task_type=task_type, estimated_minutes=minutes)
        self.refresh_all()

    def complete_selected_task(self) -> None:
        task_id = self._selected_task_id(self.today_tree)
        if not task_id:
            messagebox.showinfo("提示", "请先选择一个任务。")
            return
        task = self.store.row("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not task:
            return
        children = self.store.rows("SELECT id FROM tasks WHERE parent_id = ?", (task_id,))
        if children:
            messagebox.showwarning("项目任务", "该任务包含子任务，完成度由子任务自动决定。请完成最小子任务。")
            return
        completion = simpledialog.askfloat("完成度", "完成度 0-100：", initialvalue=100, minvalue=0, maxvalue=100, parent=self)
        if completion is None:
            return
        actual = simpledialog.askinteger("实际耗时", "实际耗时（分钟）：", initialvalue=task["estimated_minutes"], minvalue=0, parent=self) or 0
        rating = simpledialog.askinteger("自评", "自评星级 1-5：", initialvalue=4, minvalue=1, maxvalue=5, parent=self) or 4
        note = simpledialog.askstring("备注", "完成备注：", parent=self) or ""
        status = TaskStatus.COMPLETED if completion >= 100 else TaskStatus.IN_PROGRESS
        self.store.update_task_progress(task_id, completion, status=status, actual_minutes=actual)
        self.store.add_review(task_id, completion, rating, actual, note)
        amount = reward_tokens(task["estimated_minutes"], task["difficulty"], completion, actual, rating)
        self.store.add_token_ledger(task_id, "reward", amount, "完成最小任务奖励", "reward_tokens")
        self.refresh_all()

    def generate_project(self) -> None:
        goal = simpledialog.askstring("AI/本地拆分项目", "项目目标：", parent=self)
        if not goal:
            return
        deadline = simpledialog.askstring("截止日期", "截止日期（可空）：", parent=self) or ""
        available = simpledialog.askstring("可用时间", "每天/每周可投入时间（可空）：", parent=self) or ""
        client = AIClient(
            AIConfig(
                base_url=self.ai_base_url.get(),
                api_key=self.ai_key.get(),
                model=self.ai_model.get(),
                enabled=self.ai_enabled.get(),
            )
        )
        draft = client.generate_task_tree(goal, deadline, available)
        preview = json.dumps(draft, ensure_ascii=False, indent=2)
        if not messagebox.askyesno("确认写入任务树", f"将写入以下任务草稿：\n\n{preview[:3000]}"):
            return
        self._insert_task_tree(draft, None, deadline)
        self.refresh_all()

    def _insert_task_tree(self, node: dict[str, Any], parent_id: int | None, deadline: str = "") -> int:
        children = node.get("children") or []
        task_type = TaskType.PROJECT if children else TaskType.MINIMUM
        task_id = self.store.create_task(
            title=node.get("title") or "未命名任务",
            description=node.get("description") or "",
            task_type=task_type,
            parent_id=parent_id,
            estimated_minutes=int(node.get("estimatedMinutes") or 20),
            difficulty=int(node.get("difficulty") or 1),
            deadline=deadline or None,
            acceptance_criteria="\n".join(node.get("acceptanceCriteria") or []),
        )
        for child in children:
            self._insert_task_tree(child, task_id, deadline)
        self.store.recalculate_ancestors(task_id)
        return task_id

    def recalculate_selected_project(self) -> None:
        task_id = self._selected_task_id(self.project_tree)
        if task_id:
            self.store.recalculate_ancestors(task_id)
            self.refresh_all()

    def add_card(self) -> None:
        front = simpledialog.askstring("新增卡片", "正面：", parent=self)
        if not front:
            return
        back = simpledialog.askstring("新增卡片", "背面：", parent=self)
        if not back:
            return
        deck = self.store.row("SELECT id FROM decks ORDER BY id LIMIT 1")
        self.store.create_card(int(deck["id"]), front, back)
        self.refresh_all()

    def review_card(self, quality: str) -> None:
        selection = self.card_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择卡片。")
            return
        card_id = int(self.card_tree.item(selection[0], "values")[0])
        card = self.store.row("SELECT * FROM memory_cards WHERE id = ?", (card_id,))
        if not card:
            return
        if quality == "wrong":
            review_count = int(card["review_count"])
            wrong_count = int(card["wrong_count"]) + 1
            status = "reviewing"
            memory_value = max(0, float(card["memory_value"]) - 30)
        else:
            review_count = int(card["review_count"]) + 1
            wrong_count = int(card["wrong_count"])
            status = "permanent" if review_count >= 7 else "reviewing"
            memory_value = 100
        next_at = next_review_at(review_count, quality).replace(microsecond=0).isoformat()
        self.store.connection.execute(
            """
            UPDATE memory_cards
            SET review_count = ?, wrong_count = ?, memory_value = ?, next_review_at = ?,
                last_review_at = datetime('now'), status = ?
            WHERE id = ?
            """,
            (review_count, wrong_count, memory_value, next_at, status, card_id),
        )
        self.store.connection.commit()
        self.refresh_cards()

    def import_cards_csv(self) -> None:
        path = filedialog.askopenfilename(title="导入CSV", filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if path:
            count = self.store.import_cards_csv(Path(path))
            messagebox.showinfo("导入完成", f"已导入 {count} 张卡片。")
            self.refresh_cards()

    def export_cards_csv(self) -> None:
        path = filedialog.asksaveasfilename(title="导出CSV", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            self.store.export_cards_csv(Path(path))
            messagebox.showinfo("导出完成", path)

    def import_cards_apkg(self) -> None:
        path = filedialog.askopenfilename(title="导入APKG", filetypes=[("Anki Package", "*.apkg"), ("All", "*.*")])
        if path:
            count = self.store.import_cards_apkg(Path(path))
            messagebox.showinfo("导入完成", f"已导入 {count} 张APKG卡片。")
            self.refresh_cards()

    def export_cards_apkg(self) -> None:
        path = filedialog.asksaveasfilename(title="导出APKG", defaultextension=".apkg", filetypes=[("Anki Package", "*.apkg")])
        if path:
            self.store.export_cards_apkg(Path(path))
            messagebox.showinfo("导出完成", path)

    def save_note(self) -> None:
        title = self.note_title.get().strip() or "未命名杂记"
        content = self.note_text.get("1.0", "end").strip()
        now = self.store.row("SELECT datetime('now') AS now")["now"]
        self.store.connection.execute(
            "INSERT INTO notes(title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (title, content, now, now),
        )
        self.store.connection.commit()
        messagebox.showinfo("已保存", "Markdown杂记已保存到本地数据库。")

    def export_backup(self) -> None:
        path = filedialog.asksaveasfilename(title="导出JSON备份", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            self.store.export_backup_json(Path(path))
            messagebox.showinfo("导出完成", path)

    def destroy(self) -> None:
        self.store.close()
        super().destroy()


def main() -> None:
    MissionApp().mainloop()


if __name__ == "__main__":
    main()
