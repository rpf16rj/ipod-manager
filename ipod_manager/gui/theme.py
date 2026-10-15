"""Tema visual do iPod Manager — paleta, stylesheet QSS e animações.

Tema escuro moderno com acento verde (referência a apps de música).
Aplicado em ``QApplication.setStyleSheet`` no ``main()``.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QProgressBar, QWidget

# Paleta
BG_DARK = "#14171d"
BG_PANEL = "#1b1f27"
BG_INPUT = "#10131a"
BG_HOVER = "#272d38"
BORDER = "#2a2f3a"
TEXT = "#e2e8f0"
TEXT_DIM = "#8b93a3"
ACCENT = "#22c55e"        # verde
ACCENT_2 = "#38bdf8"      # ciano
DANGER = "#ef4444"
WARNING = "#f59e0b"

APP_STYLESHEET = f"""
QWidget {{
    background-color: {BG_DARK};
    color: {TEXT};
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 9pt;
}}

/* ---- Janela / painéis ---- */
QMainWindow::separator {{
    background: {BORDER};
    width: 4px;
    height: 4px;
}}
QDockWidget {{
    color: {TEXT};
    titlebar-close-icon: none;
    font-weight: bold;
}}
QDockWidget::title {{
    background: {BG_PANEL};
    padding: 6px 10px;
    border-bottom: 1px solid {BORDER};
}}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}

/* ---- Toolbar ---- */
QToolBar {{
    background: {BG_PANEL};
    border: none;
    border-bottom: 1px solid {BORDER};
    spacing: 6px;
    padding: 6px;
}}
QToolBar::separator {{
    background: {BORDER};
    width: 1px;
    margin: 6px 4px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
    color: {TEXT};
}}
QToolButton:hover {{ background: {BG_HOVER}; border-color: {BORDER}; }}
QToolButton:pressed {{ background: {ACCENT}; color: #06210f; }}
QToolButton:checked {{
    background: {ACCENT};
    color: #06210f;
    font-weight: bold;
}}
QToolButton:disabled {{ color: {TEXT_DIM}; }}
QToolButton#saveButton {{
    background: {ACCENT};
    color: #06210f;
    font-weight: bold;
}}
QToolButton#saveButton:hover {{ background: #4ade80; }}
QToolButton#saveButton:disabled {{
    background: {BG_HOVER};
    color: {TEXT_DIM};
    font-weight: normal;
}}

/* ---- Botões ---- */
QPushButton {{
    background: {BG_HOVER};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #323a48; border-color: #3b4353; }}
QPushButton:pressed {{ background: {ACCENT}; color: #06210f; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background: {BG_PANEL}; }}
QPushButton#accentButton {{
    background: {ACCENT};
    color: #06210f;
    font-weight: bold;
}}
QPushButton#accentButton:hover {{ background: #4ade80; }}
QPushButton#accentButton:disabled {{
    background: {BG_HOVER};
    color: {TEXT_DIM};
    font-weight: normal;
}}

/* ---- Tabela de músicas ---- */
QTableWidget {{
    background: {BG_INPUT};
    alternate-background-color: #191d26;
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: rgba(34, 197, 94, 0.28);
    selection-color: {TEXT};
}}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:hover {{ background: rgba(56, 189, 248, 0.12); }}
QHeaderView::section {{
    background: {BG_PANEL};
    color: {TEXT_DIM};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT};
    padding: 6px 8px;
    font-weight: bold;
    text-transform: uppercase;
    font-size: 8pt;
}}
QTableCornerButton::section {{
    background: {BG_PANEL};
    border-bottom: 2px solid {ACCENT};
}}

/* ---- Lista de playlists / fila ---- */
QListWidget {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QListWidget::item {{
    border-radius: 5px;
    padding: 7px 9px;
}}
QListWidget::item:hover {{ background: {BG_HOVER}; }}
QListWidget::item:selected {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(34,197,94,0.35), stop:1 rgba(34,197,94,0.08));
    border-left: 3px solid {ACCENT};
    color: {TEXT};
}}

/* ---- Inputs ---- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
    selection-color: #06210f;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: #06210f;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: {ACCENT};
}}

/* ---- Status bar / progresso ---- */
QStatusBar {{ background: {BG_PANEL}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
QProgressBar {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    text-align: center;
    color: {TEXT_DIM};
    height: 10px;
}}
QProgressBar::chunk {{
    border-radius: 5px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {ACCENT}, stop:1 {ACCENT_2});
}}

/* ---- Menus ---- */
QMenu {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; color: #06210f; }}
QMenu::separator {{ background: {BORDER}; height: 1px; margin: 4px 8px; }}

/* ---- Scrollbars finas ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---- Tooltip ---- */
QToolTip {{
    background: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {ACCENT};
    padding: 5px 8px;
}}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; }}
"""


def fade_in(window: QWidget, duration_ms: int = 260) -> QPropertyAnimation:
    """Animação de fade-in da janela (opacity 0 → 1)."""
    window.setWindowOpacity(0.0)
    anim = QPropertyAnimation(window, b"windowOpacity", window)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def animate_progress(
    bar: QProgressBar, value: int, duration_ms: int = 180
) -> QVariantAnimation:
    """Move a barra de progresso suavemente até ``value``."""
    anim = QVariantAnimation(bar)
    anim.setDuration(duration_ms)
    anim.setStartValue(bar.value())
    anim.setEndValue(value)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(lambda v: bar.setValue(int(v)))
    anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def flash_color_steps() -> list[QColor]:
    """Passos de cor para o "flash" de linhas recém-adicionadas."""
    return [
        QColor(34, 197, 94, 160),
        QColor(34, 197, 94, 90),
        QColor(34, 197, 94, 40),
    ]
