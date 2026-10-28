"""3m5 look & feel: colors taken from 3m5.de, Cabin as UI font."""
from __future__ import annotations

from importlib import resources

NAVY = '#032540'       # 3m5 primary dark blue (background)
NAVY_LIGHT = '#053861'  # cards / inputs
NAVY_DARK = '#021a2e'   # sidebar / header
BLUE = '#034185'        # secondary blue
HIGHLIGHT = '#42a4db'   # 3m5 accent / primary buttons
HIGHLIGHT_HOVER = '#5cb6e8'
ICE = '#c4efff'         # light accent text
TEXT = '#ffffff'
MUTED = '#8fb3cc'
DANGER = '#e5534b'

FONT_FAMILY = 'Cabin'


def asset_path(name: str) -> str:
    return str(resources.files('rl_launcher') / 'assets' / name)


def stylesheet() -> str:
    return f"""
* {{
    font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif;
    font-size: 14px;
    color: {TEXT};
}}
QMainWindow, QDialog, #central {{
    background: {NAVY};
}}
#header {{
    background: {NAVY_DARK};
    border-bottom: 1px solid {BLUE};
}}
#wordmark {{
    font-size: 26px;
    font-weight: 700;
}}
#headerSub, #muted {{
    color: {MUTED};
}}
#hero {{
    border-radius: 14px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {BLUE}, stop:1 {NAVY_LIGHT});
}}
#heroTitle {{
    font-size: 44px;
    font-weight: 700;
    letter-spacing: 2px;
}}
#heroSub {{
    color: {ICE};
    font-size: 16px;
}}
#card {{
    background: {NAVY_LIGHT};
    border-radius: 10px;
}}
#status {{
    color: {ICE};
}}
#error {{
    color: {DANGER};
}}
QPushButton {{
    background: transparent;
    border: 1px solid {HIGHLIGHT};
    border-radius: 6px;
    padding: 8px 18px;
    color: {HIGHLIGHT};
    font-weight: 600;
}}
QPushButton:hover {{
    background: rgba(66, 164, 219, 0.15);
}}
QPushButton:disabled {{
    border-color: {MUTED};
    color: {MUTED};
}}
QPushButton#primary {{
    background: {HIGHLIGHT};
    border: none;
    color: {NAVY};
    font-size: 20px;
    font-weight: 700;
    padding: 14px 48px;
    border-radius: 8px;
}}
QPushButton#primary:hover {{
    background: {HIGHLIGHT_HOVER};
}}
QPushButton#primary:disabled {{
    background: {MUTED};
    color: {NAVY};
}}
QPushButton#link {{
    border: none;
    padding: 4px;
    text-decoration: underline;
}}
QPushButton#danger {{
    border-color: {DANGER};
    color: {DANGER};
}}
QLineEdit, QComboBox, QPlainTextEdit {{
    background: {NAVY_DARK};
    border: 1px solid {BLUE};
    border-radius: 6px;
    padding: 8px;
    selection-background-color: {HIGHLIGHT};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {HIGHLIGHT};
}}
QComboBox QAbstractItemView {{
    background: {NAVY_DARK};
    selection-background-color: {BLUE};
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {HIGHLIGHT};
    border-radius: 3px;
    background: {NAVY_DARK};
}}
QCheckBox::indicator:checked {{
    background: {HIGHLIGHT};
}}
QProgressBar {{
    background: {NAVY_DARK};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {HIGHLIGHT};
    border-radius: 5px;
}}
QMessageBox QLabel {{
    color: {TEXT};
}}
QToolTip {{
    background: {NAVY_DARK};
    border: 1px solid {HIGHLIGHT};
    color: {TEXT};
}}
"""
