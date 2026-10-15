"""Smoke test de integracao: GUI offscreen + IPodService real em I:\\.

Uso: python tests\\smoke_integration.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipod_manager.ipod_service import IPodService

s = IPodService("I:\\")
di = s.device_info()
print(f"[service] {di.name} | {di.track_count} faixas | {di.playlist_count} playlists | livre {di.free_bytes//2**20} MB")
t = s.list_tracks()[0]
print(f"[service] faixa[0]: {t.title} - {t.artist} | {t.duration_ms} ms | rating {t.rating}")
pls = s.list_playlists()
print(f"[service] playlists: {[p.name for p in pls]}")

from PySide6.QtWidgets import QApplication
from ipod_manager.gui.app import MainWindow

app = QApplication.instance() or QApplication(sys.argv)
w = MainWindow()
print("[gui] MainWindow construida:", w.windowTitle())
w.show()
w.close()
print("SMOKE OK")
