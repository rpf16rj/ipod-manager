"""Teste e2e do IPodService no iPod real (I:\\).

Uso: python tests\\manual_e2e_test.py
Fluxo: add -> save -> reabre -> update_track -> save -> reabre ->
verifica -> remove -> save -> reabre -> verifica 111 faixas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipod_manager.ipod_service import IPodService

MP3 = r"C:\Users\rpf16\AppData\Local\Temp\test_tone.mp3"
MOUNT = "I:\\"

s = IPodService(MOUNT)
n0 = s.device_info().track_count
print("faixas iniciais:", n0)

# add + save
ids = s.add_files([MP3])
assert ids, s.last_errors
tid = ids[0]
s.save()
print("add ok, id:", tid)

# reabre, edita metadados, salva
s2 = IPodService(MOUNT)
assert s2.device_info().track_count == n0 + 1
s2.update_track(tid, title="E2E EDITADO", artist="Devin E2E", rating=80)
s2.save()
print("edit + save ok")

# reabre, verifica persistencia da edicao
s3 = IPodService(MOUNT)
t = [x for x in s3.list_tracks() if x.track_id == tid]
assert t, "faixa sumiu!"
print("persistiu:", t[0].title, "|", t[0].artist, "| rating:", t[0].rating)
assert t[0].title == "E2E EDITADO" and t[0].rating == 80

# remove + save
s3.remove_tracks([tid])
s3.save()

s4 = IPodService(MOUNT)
n_final = s4.device_info().track_count
resto = [x for x in s4.list_tracks() if x.track_id == tid]
print("faixas finais:", n_final, "| residuos:", len(resto))
assert n_final == n0 and not resto
print("E2E OK — add/edit/remove persistem corretamente")
