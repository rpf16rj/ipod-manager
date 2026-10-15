"""Remove do iPod faixas de teste deixadas por testes manuais."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipod_manager.ipod_service import IPodService

s = IPodService("I:\\")
alvo = [
    t.track_id
    for t in s.list_tracks()
    if t.title in {"E2E EDITADO", "TEST DEVIN", "test_tone"}
    or "pygpod" in (t.ipod_path or "")
]
print("faixas de teste encontradas:", alvo)
if alvo:
    s.remove_tracks(alvo)
    s.save()
    s2 = IPodService("I:\\")
    print("faixas agora:", s2.device_info().track_count)
else:
    print("nada a limpar")
