"""Teste manual de escrita no iPod real (I:\\).

Uso: python tests\\manual_write_test.py
Adiciona um MP3 de teste, salva, relê, remove e salva de novo.
Requer backup prévio de I:\\iPod_Control\\iTunes (feito em ipod_backup/).
"""
import sys

sys.path.insert(0, r"C:\Users\rpf16\AppData\Roaming\Python\Python314\site-packages")

from pygpod.model.database import Database

MP3 = r"C:\Users\rpf16\AppData\Local\Temp\test_tone.mp3"
MOUNT = "I:\\"

db = Database(MOUNT)
n_inicial = len(db.tracks)
print("tracks antes:", n_inicial)

t = db.add_track(MP3, title="TEST DEVIN", artist="Devin", album="Test", genre="Test")
print("adicionada id", t.track_id, "|", t.title, "| path:", t.ipod_path)
db.save()
print("save OK")

# relê do zero
db2 = Database(MOUNT)
found = [x for x in db2.tracks if x.title == "TEST DEVIN"]
print("tracks depois:", len(db2.tracks), "| teste encontrada:", len(found))
assert found, "faixa de teste nao persistiu!"

# remove e salva de novo (limpeza)
db2.remove_track(found[0], delete_file=True)
db2.save()

db3 = Database(MOUNT)
leftover = [x for x in db3.tracks if x.title == "TEST DEVIN"]
print("tracks final:", len(db3.tracks), "| residuos:", len(leftover))
assert not leftover and len(db3.tracks) == n_inicial
print("WRITE PATH OK — iPod intacto")
