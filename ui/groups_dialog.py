"""Groups manager (Phase 34): create / rename / delete groups and open a group."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core import datastore as repo
from ui.group_view_dialog import GroupViewDialog


class GroupsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Groups")
        self.resize(400, 440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Comparison groups — double-click to open."))

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self._open())
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        for label, slot in (("New…", self._new), ("Rename…", self._rename),
                            ("Delete", self._delete), ("Open", self._open)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self._reload()

    def _reload(self) -> None:
        self.list.clear()
        for group in repo.list_groups():
            item = QListWidgetItem(f"{group.name}   ({group.member_count})")
            item.setData(Qt.ItemDataRole.UserRole, (group.id, group.name))
            self.list.addItem(item)

    def _selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        if ok and name.strip():
            repo.create_group(name.strip())
            self._reload()

    def _rename(self) -> None:
        sel = self._selected()
        if not sel:
            return
        group_id, group_name = sel
        name, ok = QInputDialog.getText(self, "Rename group", "New name:", text=group_name)
        if ok and name.strip():
            repo.rename_group(group_id, name.strip())
            self._reload()

    def _delete(self) -> None:
        sel = self._selected()
        if not sel:
            return
        group_id, group_name = sel
        confirm = QMessageBox.question(
            self, "Delete group",
            f"Delete group '{group_name}'? The products themselves stay tracked.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            repo.delete_group(group_id)
            self._reload()

    def _open(self) -> None:
        sel = self._selected()
        if not sel:
            return
        group_id, group_name = sel
        GroupViewDialog(group_id, group_name, parent=self).exec()
