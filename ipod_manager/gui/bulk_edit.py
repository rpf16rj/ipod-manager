"""Diálogo de edição em massa de metadados.

Permite alterar artista/álbum/gênero/ano/avaliação em todas as faixas
selecionadas de uma vez. Cada campo tem um checkbox: só os marcados são
aplicados — os demais permanecem inalterados em cada faixa.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class BulkEditDialog(QDialog):
    """Retorna via :meth:`selected_fields` os campos marcados para edição."""

    def __init__(self, track_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Editar em massa — {track_count} música(s)")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Marque os campos que deseja alterar — o valor é "
                "aplicado a todas as músicas selecionadas."
            )
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._checks: dict[str, QCheckBox] = {}

        self._artist_edit = QLineEdit()
        form.addRow("Artista", self._field("artista", self._artist_edit))
        self._album_edit = QLineEdit()
        form.addRow("Álbum", self._field("album", self._album_edit))
        self._genre_edit = QLineEdit()
        form.addRow("Gênero", self._field("genre", self._genre_edit))

        self._year_spin = QSpinBox()
        self._year_spin.setRange(0, 2100)
        self._year_spin.setSpecialValueText("—")
        self._year_spin.setValue(0)
        form.addRow("Ano", self._field("year", self._year_spin))

        self._rating_combo = QComboBox()
        self._rating_combo.addItem("Sem avaliação", 0)
        for stars in range(1, 6):
            self._rating_combo.addItem("★" * stars, stars * 20)
        self._rating_combo.setCurrentIndex(0)
        form.addRow("Avaliação", self._field("rating", self._rating_combo))

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _field(self, key: str, widget: QWidget) -> QWidget:
        """Checkbox + widget num container; widget só habilita marcado."""
        chk = QCheckBox()
        chk.setToolTip("Aplicar este campo às músicas selecionadas")
        widget.setEnabled(False)
        chk.toggled.connect(widget.setEnabled)
        self._checks[key] = chk
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(chk)
        row.addWidget(widget, stretch=1)
        return container

    def selected_fields(self) -> dict:
        """Campos marcados → ``{field: value}`` para ``update_track``."""
        out: dict = {}
        if self._checks["artista"].isChecked():
            out["artist"] = self._artist_edit.text().strip()
        if self._checks["album"].isChecked():
            out["album"] = self._album_edit.text().strip()
        if self._checks["genre"].isChecked():
            out["genre"] = self._genre_edit.text().strip()
        if self._checks["year"].isChecked():
            out["year"] = int(self._year_spin.value())
        if self._checks["rating"].isChecked():
            out["rating"] = int(self._rating_combo.currentData() or 0)
        return out
