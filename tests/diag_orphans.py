"""Diagnostica arquivos orfaos em iPod_Control\\Music (sem entrada no iTunesDB).

Uso: python tests\\diag_orphans.py           # so lista
     python tests\\diag_orphans.py --delete  # apaga orfaos
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pygpod.model.database import Database
from pygpod.utils.encoding import ipod_path_to_os

MOUNT = "I:\\"
MUSIC_DIR = os.path.join(MOUNT, "iPod_Control", "Music")

db = Database(MOUNT)
refs = {
    os.path.normcase(os.path.normpath(ipod_path_to_os(t.ipod_path, MOUNT)))
    for t in db.tracks
}
print(f"DB: {len(db.tracks)} faixas, {len(refs)} paths referenciados")

orphans, orphan_bytes = [], 0
for root, _dirs, files in os.walk(MUSIC_DIR):
    for f in files:
        p = os.path.join(root, f)
        if os.path.normcase(os.path.normpath(p)) not in refs:
            orphans.append(p)
            orphan_bytes += os.path.getsize(p)

print(f"orfaos: {len(orphans)} arquivos, {orphan_bytes/2**20:.1f} MB")
for p in orphans[:10]:
    print("  ", p)
if len(orphans) > 10:
    print(f"   ... e mais {len(orphans)-10}")

if "--delete" in sys.argv:
    for p in orphans:
        os.unlink(p)
    print("orfaos apagados")
