import json
import os
import copy
from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QSplitter,
    QPlainTextEdit, QGroupBox, QMessageBox, QDialog,
    QDialogButtonBox, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence, QBrush, QColor

from models.config_entry import ConfigEntry
from parsers.config_parser import ConfigParser
from core.conflict_detector import ConflictDetector


class EditDialog(QDialog):
    def __init__(self, entry: ConfigEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"编辑: {entry.key}")
        self.setMinimumSize(500, 220)
        self.setModal(True)

        self._entry = entry
        self._result = None

        layout = QVBoxLayout(self)

        key_label = QLabel(f"参数: {entry.key}")
        key_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(key_label)

        layout.addWidget(QLabel("当前值:"))

        self._text = QPlainTextEdit()
        self._text.setPlainText(entry.value)
        self._text.setMaximumHeight(120)
        layout.addWidget(self._text)

        if entry.comment:
            comment_label = QLabel(f"注释: {entry.comment}")
            comment_label.setStyleSheet("color: gray;")
            layout.addWidget(comment_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._text.setFocus()

    def _accept(self):
        self._result = self._text.toPlainText().strip()
        self.accept()

    def get_result(self):
        return self._result


class AddEntryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加配置项")
        self.setMinimumSize(400, 180)
        self.setModal(True)

        self._key = ""
        self._value = ""

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("参数名:"))
        self._key_edit = QLineEdit()
        layout.addWidget(self._key_edit)

        layout.addWidget(QLabel("值:"))
        self._value_edit = QLineEdit()
        layout.addWidget(self._value_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._key_edit.setFocus()

    def _accept(self):
        self._key = self._key_edit.text().strip()
        self._value = self._value_edit.text().strip()
        if not self._key:
            QMessageBox.warning(self, "输入错误", "参数名不能为空")
            return
        self.accept()

    def get_key(self):
        return self._key

    def get_value(self):
        return self._value


class ConfigEditorTab(QWidget):
    loaded = pyqtSignal(str)
    saved = pyqtSignal(str)
    modified_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._entries: List[ConfigEntry] = []
        self._entry_map: Dict[int, ConfigEntry] = {}
        self._undo_stack: List[tuple] = []
        self._original_hash = None
        self._conflict_detector = ConflictDetector()
        self._file_path: str = ""

        self._path_aliases: Dict[str, str] = {}
        self._load_path_aliases()

        self._sftp = None
        self._sudo_executor = None
        self._backup_manager = None
        self._sudo_password = ""

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索参数名或值...")
        self._search_edit.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self._search_edit)

        self._add_btn = QPushButton("添加")
        self._add_btn.clicked.connect(self._do_add)
        toolbar.addWidget(self._add_btn)

        self._delete_btn = QPushButton("删除")
        self._delete_btn.clicked.connect(self._do_delete)
        toolbar.addWidget(self._delete_btn)

        self._undo_btn = QPushButton("撤销")
        self._undo_btn.clicked.connect(self._do_undo)
        self._undo_btn.setEnabled(False)
        toolbar.addWidget(self._undo_btn)

        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["参数名", "当前值", "类型"])
        self._tree.setColumnWidth(0, 200)
        self._tree.setColumnWidth(1, 300)
        self._tree.setColumnWidth(2, 80)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.setRootIsDecorated(False)
        self._tree.itemSelectionChanged.connect(self._on_tree_select)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_click)

        left_layout.addWidget(self._tree)
        splitter.addWidget(left)

        right = QGroupBox("快速编辑")
        right_layout = QVBoxLayout(right)

        right_layout.addWidget(QLabel("选中参数:"))
        self._edit_key_label = QLabel("(未选择)")
        self._edit_key_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        right_layout.addWidget(self._edit_key_label)

        right_layout.addWidget(QLabel("值:"))
        self._edit_value = QPlainTextEdit()
        self._edit_value.setMaximumHeight(200)
        self._edit_value.setEnabled(False)
        right_layout.addWidget(self._edit_value)

        btn_layout = QHBoxLayout()
        self._apply_btn = QPushButton("应用修改")
        self._apply_btn.clicked.connect(self._do_apply_edit)
        self._apply_btn.setEnabled(False)
        btn_layout.addWidget(self._apply_btn)

        self._reset_btn = QPushButton("重置")
        self._reset_btn.clicked.connect(self._do_reset_edit)
        self._reset_btn.setEnabled(False)
        btn_layout.addWidget(self._reset_btn)

        right_layout.addLayout(btn_layout)
        right_layout.addStretch()

        self._save_btn = QPushButton("保存到远程")
        self._save_btn.clicked.connect(self.do_save)
        self._save_btn.setEnabled(False)
        right_layout.addWidget(self._save_btn)

        splitter.addWidget(right)
        splitter.setSizes([600, 350])

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._do_undo)

    def set_services(self, sftp, sudo_executor, backup_manager):
        self._sftp = sftp
        self._sudo_executor = sudo_executor
        self._backup_manager = backup_manager

    def set_sudo_password(self, password: str):
        self._sudo_password = password

    def _load_path_aliases(self):
        try:
            import sys
            app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else \
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            alias_file = os.path.join(app_dir, "path_aliases.json")
            if os.path.isfile(alias_file):
                with open(alias_file, 'r', encoding='utf-8') as f:
                    self._path_aliases = json.load(f)
        except Exception:
            self._path_aliases = {}

    def load_file(self, remote_path: str):
        if not self._sftp:
            return
        self._file_path = remote_path
        self._entries = []
        self._entry_map.clear()
        self._undo_stack.clear()

        try:
            raw_bytes = self._sftp.read_file(remote_path)
            text_content = raw_bytes.decode('utf-8')
            self._entries = ConfigParser.parse(text_content)
            self._refresh_tree()
            self._conflict_detector.record_state(raw_bytes)
            self._save_btn.setEnabled(True)
            self.loaded.emit(remote_path)
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"无法读取远程文件: {str(e)}")

    def load_from_content(self, content: str, file_path: str = ""):
        self._file_path = file_path
        self._entries = ConfigParser.parse(content)
        self._entry_map.clear()
        self._undo_stack.clear()
        self._refresh_tree()
        self._conflict_detector.record_state(content.encode('utf-8'))
        self._save_btn.setEnabled(True)

    def get_content(self) -> str:
        return ConfigParser.generate(self._entries)

    def _refresh_tree(self):
        self._tree.clear()
        self._entry_map.clear()

        filter_text = self._search_edit.text().lower() if self._search_edit else ""
        modified_indices = {t[0] for t in self._undo_stack}

        for i, entry in enumerate(self._entries):
            if filter_text:
                if filter_text not in entry.key.lower() and filter_text not in entry.value.lower():
                    continue

            item = QTreeWidgetItem()
            item.setData(0, Qt.ItemDataRole.UserRole, i)

            is_modified = i in modified_indices

            if entry.is_empty:
                item.setText(0, "(空行)")
                item.setText(1, "")
                item.setText(2, "空行")
                item.setForeground(0, QBrush(QColor("#999999")))
            elif entry.is_section:
                item.setText(0, f"[{entry.key}]")
                item.setText(1, "")
                item.setText(2, "段落")
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setBackground(0, QBrush(QColor("#e3f2fd")))
            elif entry.comment and not entry.key:
                item.setText(0, entry.comment)
                item.setText(1, "")
                item.setText(2, "注释")
                item.setForeground(0, QBrush(QColor("#888888")))
            else:
                item.setText(0, entry.key)
                item.setText(1, entry.value)
                item.setText(2, "参数")
                if is_modified:
                    item.setBackground(0, QBrush(QColor("#fff3cd")))
                    item.setBackground(1, QBrush(QColor("#fff3cd")))

            self._tree.addTopLevelItem(item)
            self._entry_map[id(item)] = i

    def _apply_filter(self):
        self._refresh_tree()

    def _on_tree_select(self):
        selected = self._tree.selectedItems()
        if not selected:
            self._edit_key_label.setText("(未选择)")
            self._edit_value.setPlainText("")
            self._edit_value.setEnabled(False)
            self._apply_btn.setEnabled(False)
            self._reset_btn.setEnabled(False)
            return

        item = selected[0]
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            return

        entry = self._entries[idx]
        if entry.is_empty or entry.is_section or (entry.comment and not entry.key):
            self._edit_key_label.setText(entry.key or entry.comment or "(空行)")
            self._edit_value.setPlainText("")
            self._edit_value.setEnabled(False)
            self._apply_btn.setEnabled(False)
            self._reset_btn.setEnabled(False)
            return

        self._edit_key_label.setText(entry.key)
        self._edit_value.setPlainText(entry.value)
        self._edit_value.setEnabled(True)
        self._apply_btn.setEnabled(True)
        self._reset_btn.setEnabled(True)

    def _on_tree_double_click(self, item: QTreeWidgetItem, column: int):
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        entry = self._entries[idx]
        if entry.is_empty or entry.is_section or (entry.comment and not entry.key):
            return

        dlg = EditDialog(entry, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_value = dlg.get_result()
            if new_value != entry.value:
                self._undo_stack.append((idx, copy.deepcopy(entry)))
                entry.value = new_value
                self._refresh_tree()
                self._undo_btn.setEnabled(True)
                self.modified_changed.emit(True)

    def _do_apply_edit(self):
        selected = self._tree.selectedItems()
        if not selected:
            return
        item = selected[0]
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        entry = self._entries[idx]
        new_value = self._edit_value.toPlainText().strip()

        if new_value != entry.value:
            self._undo_stack.append((idx, copy.deepcopy(entry)))
            entry.value = new_value
            self._refresh_tree()
            self._undo_btn.setEnabled(True)
            self.modified_changed.emit(True)

    def _do_reset_edit(self):
        selected = self._tree.selectedItems()
        if not selected:
            return
        item = selected[0]
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        self._edit_value.setPlainText(self._entries[idx].value)

    def _do_undo(self):
        if not self._undo_stack:
            return
        item = self._undo_stack.pop()
        if len(item) == 2:
            idx, old_entry = item
            op = "edit"
        else:
            idx, old_entry, op = item

        if op == "add":
            self._entries.pop(idx)
        elif op == "delete":
            self._entries.insert(idx, old_entry)
        else:
            self._entries[idx] = old_entry

        self._refresh_tree()
        if not self._undo_stack:
            self._undo_btn.setEnabled(False)

    def _do_add(self):
        dlg = AddEntryDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry = ConfigEntry(
                key=dlg.get_key(),
                value=dlg.get_value(),
                line_number=len(self._entries) + 1
            )
            self._entries.append(entry)
            self._undo_stack.append((len(self._entries) - 1, entry, "add"))
            self._refresh_tree()
            self._undo_btn.setEnabled(True)
            self.modified_changed.emit(True)

    def _do_delete(self):
        selected = self._tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选择要删除的项")
            return
        item = selected[0]
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            return

        entry = self._entries[idx]
        if entry.is_empty or entry.is_section or (entry.comment and not entry.key):
            self._undo_stack.append((idx, copy.deepcopy(entry), "delete"))
            self._entries.pop(idx)
            self._refresh_tree()
            self._undo_btn.setEnabled(True)
            self.modified_changed.emit(True)
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除参数 \"{entry.key}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._undo_stack.append((idx, copy.deepcopy(entry), "delete"))
            self._entries.pop(idx)
            self._refresh_tree()
            self._undo_btn.setEnabled(True)
            self.modified_changed.emit(True)

    def do_save(self) -> bool:
        if not self._file_path:
            QMessageBox.warning(self, "提示", "未设置远程文件路径")
            return False

        content = ConfigParser.generate(self._entries)

        if self._backup_manager and self._sudo_executor:
            try:
                self._backup_manager.create_backup(self._file_path, self._sudo_password)
            except Exception as e:
                reply = QMessageBox.question(
                    self, "备份失败",
                    f"{str(e)}\n\n是否跳过备份，直接保存？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return False

        try:
            if self._sudo_executor and self._sudo_password:
                self._sudo_executor.write_file_sudo(
                    self._file_path, content, self._sudo_password
                )
            elif self._sftp:
                self._sftp.write_file(self._file_path, content.encode('utf-8'))
            self._conflict_detector.record_state(content.encode('utf-8'))
            self._undo_stack.clear()
            self._undo_btn.setEnabled(False)
            self.modified_changed.emit(False)
            self.saved.emit(self._file_path)
            QMessageBox.information(self, "保存成功", "文件已保存到远程服务器。")
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return False

    def has_unsaved_changes(self) -> bool:
        return len(self._undo_stack) > 0

    def set_connected(self, connected: bool):
        if not connected:
            self._tree.clear()
            self._entry_map.clear()
            self._entries = []
            self._undo_stack.clear()
            self._edit_key_label.setText("(未选择)")
            self._edit_value.setPlainText("")
            self._edit_value.setEnabled(False)
            self._apply_btn.setEnabled(False)
            self._reset_btn.setEnabled(False)
            self._undo_btn.setEnabled(False)
            self._save_btn.setEnabled(False)
            self._conflict_detector.reset()
