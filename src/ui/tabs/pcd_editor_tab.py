import copy
import json
import os
from datetime import datetime
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QSplitter,
    QGroupBox, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QBrush, QColor

from models.pcd_model import PCDDocument, Group, Point
from parsers.pcd_parser import parse_pcd, groups_to_text
from core.conflict_detector import ConflictDetector


class PCDEditorTab(QWidget):
    loaded = pyqtSignal(str)
    saved = pyqtSignal(str)
    group_modified = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._document: Optional[PCDDocument] = None
        self._original_groups: List[Group] = []
        self._selected_idx: int = -1
        self._group_status: List[str] = []
        self._edit_lines: List[List[QLineEdit]] = []
        self._readonly_labels: List[List[QLabel]] = []
        self._curvature_labels: List[QLabel] = []
        self._conflict_detector = ConflictDetector()
        self._file_path: str = ""

        self._sftp = None
        self._sudo_executor = None
        self._backup_manager = None
        self._sudo_password = ""

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        list_group = QGroupBox("点组列表 (每4个点为一组)")
        list_layout = QVBoxLayout(list_group)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["组号", "坐标范围 (x / y)", "状态"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_group_select)
        self._table.cellDoubleClicked.connect(lambda r, c: self._load_group_to_edit())

        list_layout.addWidget(self._table)
        left_layout.addWidget(list_group)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        edit_group = QGroupBox("编辑选中组")
        edit_layout = QVBoxLayout(edit_group)

        self._point_frames = []
        self._edit_lines = []
        self._readonly_labels = []
        self._curvature_labels = []

        for pt_idx in range(4):
            pt_group = QGroupBox(f"点 {pt_idx + 1}")
            pt_layout = QVBoxLayout(pt_group)

            coords = QHBoxLayout()
            pt_lines = []
            for label_text in ("x", "y", "z"):
                coords.addWidget(QLabel(f"{label_text}:"))
                edit = QLineEdit()
                edit.setPlaceholderText("0.00000")
                edit.setMaximumWidth(120)
                validator = QDoubleValidator()
                validator.setNotation(QDoubleValidator.Notation.StandardNotation)
                edit.setValidator(validator)
                edit.setEnabled(False)
                coords.addWidget(edit)
                coords.addStretch()
                pt_lines.append(edit)
            self._edit_lines.append(pt_lines)
            pt_layout.addLayout(coords)

            normal_row = QHBoxLayout()
            readonly_vars = []
            for label_text in ("normal_x", "normal_y", "normal_z"):
                normal_row.addWidget(QLabel(f"{label_text}:"))
                lbl = QLabel("0")
                lbl.setStyleSheet(
                    "background-color: #f0f0f0; border: 1px solid #ccc; "
                    "padding: 2px 6px; min-width: 80px;"
                )
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                normal_row.addWidget(lbl)
                normal_row.addStretch()
                readonly_vars.append(lbl)
            self._readonly_labels.append(readonly_vars)
            pt_layout.addLayout(normal_row)

            curv_row = QHBoxLayout()
            curv_row.addWidget(QLabel("curvature:"))
            curv_lbl = QLabel("0")
            curv_lbl.setStyleSheet(
                "background-color: #f0f0f0; border: 1px solid #ccc; "
                "padding: 2px 6px; min-width: 80px;"
            )
            curv_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            curv_row.addWidget(curv_lbl)
            curv_row.addStretch()
            self._curvature_labels.append(curv_lbl)
            pt_layout.addLayout(curv_row)

            edit_layout.addWidget(pt_group)
            self._point_frames.append(pt_group)

        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton("应用修改")
        self._apply_btn.clicked.connect(self._do_apply_edit)
        self._apply_btn.setEnabled(False)
        btn_row.addWidget(self._apply_btn)

        self._undo_group_btn = QPushButton("撤销本组")
        self._undo_group_btn.clicked.connect(self._do_undo_group)
        self._undo_group_btn.setEnabled(False)
        btn_row.addWidget(self._undo_group_btn)

        edit_layout.addLayout(btn_row)

        save_btn = QPushButton("保存到远程")
        save_btn.clicked.connect(self.do_save)
        save_btn.setEnabled(False)
        edit_layout.addWidget(save_btn)
        self._save_btn = save_btn
        right_layout.addWidget(edit_group)

        splitter.addWidget(right)
        splitter.setSizes([400, 600])

    def set_services(self, sftp, sudo_executor, backup_manager):
        self._sftp = sftp
        self._sudo_executor = sudo_executor
        self._backup_manager = backup_manager

    def set_sudo_password(self, password: str):
        self._sudo_password = password

    def set_connected(self, connected: bool):
        if not connected:
            self._document = None
            self._original_groups = []
            self._group_status = []
            self._selected_idx = -1
            self._table.setRowCount(0)
            self._clear_edit_panel()
            self._save_btn.setEnabled(False)
            self._conflict_detector.reset()

    def load_file(self, remote_path: str):
        if not self._sftp:
            return
        self._file_path = remote_path
        try:
            raw_bytes = self._sftp.read_file(remote_path)
            text_content = raw_bytes.decode('utf-8')
            self._document = parse_pcd(text_content)
            self._original_groups = copy.deepcopy(self._document.groups)
            self._group_status = ["未修改"] * len(self._document.groups)
            self._selected_idx = -1

            self._populate_table()
            self._clear_edit_panel()
            self._conflict_detector.record_state(raw_bytes)
            self._save_btn.setEnabled(True)
            self.loaded.emit(remote_path)
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"无法读取/解析PCD文件: {str(e)}")

    def load_from_content(self, content: str, file_path: str = ""):
        self._file_path = file_path
        try:
            self._document = parse_pcd(content)
            self._original_groups = copy.deepcopy(self._document.groups)
            self._group_status = ["未修改"] * len(self._document.groups)
            self._selected_idx = -1
            self._populate_table()
            self._clear_edit_panel()
            self._save_btn.setEnabled(True)
            self._conflict_detector.record_state(content.encode('utf-8'))
        except Exception as e:
            QMessageBox.critical(self, "解析失败", f"PCD文件解析失败: {str(e)}")

    def get_content(self) -> str:
        if self._document:
            return groups_to_text(self._document)
        return ""

    def _populate_table(self):
        self._table.setRowCount(0)
        if not self._document:
            return

        for group in self._document.groups:
            xs = [p.x for p in group.points]
            ys = [p.y for p in group.points]
            x_range = f"x: {min(xs):.3f} ~ {max(xs):.3f}"
            y_range = f"y: {min(ys):.3f} ~ {max(ys):.3f}"
            range_str = f"{x_range}    {y_range}"
            status = self._group_status[group.index]

            row = self._table.rowCount()
            self._table.insertRow(row)

            idx_item = QTableWidgetItem(str(group.index))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, idx_item)

            range_item = QTableWidgetItem(range_str)
            self._table.setItem(row, 1, range_item)

            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "已修改(未保存)":
                status_item.setBackground(QBrush(QColor("#fff3cd")))
            self._table.setItem(row, 2, status_item)

    def _on_group_select(self):
        if not self._document:
            return
        selected = self._table.selectedItems()
        if not selected:
            return
        self._load_group_to_edit()

    def _load_group_to_edit(self):
        selected = self._table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        if not self._document or row >= len(self._document.groups):
            return

        self._selected_idx = row
        group = self._document.groups[row]

        for pt_idx in range(4):
            if pt_idx < len(group.points):
                p = group.points[pt_idx]
                self._edit_lines[pt_idx][0].setText(str(p.x))
                self._edit_lines[pt_idx][1].setText(str(p.y))
                self._edit_lines[pt_idx][2].setText(str(p.z))
                self._readonly_labels[pt_idx][0].setText(str(p.normal_x))
                self._readonly_labels[pt_idx][1].setText(str(p.normal_y))
                self._readonly_labels[pt_idx][2].setText(str(p.normal_z))
                self._curvature_labels[pt_idx].setText(str(p.curvature))
            else:
                for i in range(3):
                    self._edit_lines[pt_idx][i].setText("")
                    self._edit_lines[pt_idx][i].setEnabled(False)
                for i in range(3):
                    self._readonly_labels[pt_idx][i].setText("")
                self._curvature_labels[pt_idx].setText("")
                continue

            for i in range(3):
                self._edit_lines[pt_idx][i].setEnabled(True)

        self._apply_btn.setEnabled(True)
        self._undo_group_btn.setEnabled(True)

    def _clear_edit_panel(self):
        for pt_idx in range(4):
            for i in range(3):
                self._edit_lines[pt_idx][i].setText("")
                self._edit_lines[pt_idx][i].setEnabled(False)
                self._readonly_labels[pt_idx][i].setText("0")
            self._curvature_labels[pt_idx].setText("0")
        self._selected_idx = -1
        self._apply_btn.setEnabled(False)
        self._undo_group_btn.setEnabled(False)

    def _do_apply_edit(self):
        if self._selected_idx < 0 or not self._document:
            return

        idx = self._selected_idx
        group = self._document.groups[idx]

        try:
            for pt_idx in range(len(group.points)):
                x_str = self._edit_lines[pt_idx][0].text().strip()
                y_str = self._edit_lines[pt_idx][1].text().strip()
                z_str = self._edit_lines[pt_idx][2].text().strip()
                if not x_str or not y_str or not z_str:
                    raise ValueError(f"点 {pt_idx + 1} 的 x/y/z 不能为空")
                group.points[pt_idx].x = float(x_str)
                group.points[pt_idx].y = float(y_str)
                group.points[pt_idx].z = float(z_str)
        except ValueError as e:
            QMessageBox.warning(self, "数值错误", str(e))
            return

        self._group_status[idx] = "已修改(未保存)"
        self._update_table_status(idx)
        self._load_group_to_edit()
        self.group_modified.emit(idx)

    def _do_undo_group(self):
        if self._selected_idx < 0 or not self._document or not self._original_groups:
            return

        idx = self._selected_idx
        original = copy.deepcopy(self._original_groups[idx])
        self._document.groups[idx] = original
        self._group_status[idx] = "未修改"
        self._update_table_status(idx)
        self._load_group_to_edit()

    def _do_undo_all(self):
        if not self._document or not self._original_groups:
            return
        reply = QMessageBox.question(
            self, "确认撤销",
            "确定撤销所有修改？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._document.groups = copy.deepcopy(self._original_groups)
            self._group_status = ["未修改"] * len(self._document.groups)
            self._populate_table()
            self._clear_edit_panel()

    def do_save(self) -> bool:
        if not self._document or not self._file_path:
            return False

        modified_count = sum(1 for s in self._group_status if s == "已修改(未保存)")
        if modified_count == 0:
            QMessageBox.information(self, "无需保存", "没有需要保存的修改。")
            return False

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
            new_content = groups_to_text(self._document)
            if self._sudo_executor and self._sudo_password:
                self._sudo_executor.write_file_sudo(
                    self._file_path, new_content, self._sudo_password
                )
            elif self._sftp:
                self._sftp.write_file(self._file_path, new_content.encode('utf-8'))

            self._original_groups = copy.deepcopy(self._document.groups)
            self._group_status = ["未修改"] * len(self._document.groups)
            self._conflict_detector.record_state(new_content.encode('utf-8'))
            self._populate_table()
            self.saved.emit(self._file_path)
            QMessageBox.information(self, "保存成功", "文件已保存到远程服务器。")
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return False

    def _update_table_status(self, group_index: int):
        status = self._group_status[group_index]
        item = self._table.item(group_index, 2)
        if item:
            item.setText(status)
            if status == "已修改(未保存)":
                item.setBackground(QBrush(QColor("#fff3cd")))
            else:
                item.setBackground(QBrush(Qt.GlobalColor.white))

    def has_unsaved_changes(self) -> bool:
        return any(s == "已修改(未保存)" for s in self._group_status)
