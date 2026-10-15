"""Teste da conversao FLAC->MP3 em iPod fake (init_ipod numa pasta temp).

Uso: python tests\\manual_convert_test.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import imageio_ffmpeg
from pygpod.device.mountpoint import init_ipod

from ipod_manager.ipod_service import IPodService

fake = os.path.join(tempfile.gettempdir(), "ipodmgr_fake_ipod")
shutil.rmtree(fake, ignore_errors=True)
os.makedirs(fake)
init_ipod(fake, model="classic_6g")
print("iPod fake criado em", fake)

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
flac = os.path.join(tempfile.gettempdir(), "test_tone.flac")
import subprocess
subprocess.run(
    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
     "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
     "-codec:a", "flac", flac],
    check=True,
)
print("flac de teste:", os.path.getsize(flac), "bytes")

s = IPodService(fake)
# sem ffmpeg -> deve falhar em last_errors
ids = s.add_files([flac])
print("sem ffmpeg: ids=", ids, "| erros:", s.last_errors)
assert not ids and s.last_errors

# com ffmpeg -> converte e adiciona
ids = s.add_files([flac], ffmpeg_path=ffmpeg)
print("com ffmpeg: ids=", ids, "| erros:", s.last_errors)
assert ids, s.last_errors
s.save()

s2 = IPodService(fake)
print("faixas no fake:", s2.device_info().track_count)
assert s2.device_info().track_count == 1

shutil.rmtree(fake, ignore_errors=True)
print("CONVERSAO OK")
