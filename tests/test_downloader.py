"""Testes do módulo ipod_manager.downloader.

Testes de busca/playlist usam a rede real (YouTube Music público, sem auth)
e fazem ``pytest.skip`` quando não há conectividade ou a API falha.
O teste de download real é marcado como ``slow`` — rode com
``python -m pytest tests/test_downloader.py -m "not slow"`` para pulá-lo.
"""

import os
import tempfile

import pytest

from ipod_manager.downloader import Downloader, YTMusicClient, YTTrack

# Playlist pública estável do YouTube Music ("Top 100 Music Videos Global").
PLAYLIST_ID = "PL4fGSI1pDJn5kI81J1fYWK5eZRl1zJ5kM"
PLAYLIST_URL = f"https://music.youtube.com/playlist?list={PLAYLIST_ID}"


def test_search():
    """Busca por texto retorna resultados com video_id e título."""
    client = YTMusicClient()
    try:
        results = client.search("daft punk", limit=5)
    except Exception as exc:
        pytest.skip(f"sem acesso ao YouTube Music: {exc}")
    assert len(results) >= 1
    primeiro = results[0]
    assert primeiro.video_id
    assert primeiro.title
    assert isinstance(primeiro.duration_s, int)


def test_playlist():
    """Playlist pública retorna (nome, faixas); aceita URL completa."""
    client = YTMusicClient()
    try:
        nome, tracks = client.playlist_tracks(PLAYLIST_URL)
    except Exception as exc:
        pytest.skip(f"playlist indisponível ou sem rede: {exc}")
    assert nome
    assert len(tracks) >= 1
    assert all(t.video_id for t in tracks)
    assert all(isinstance(t, YTTrack) for t in tracks)


@pytest.mark.slow
def test_download():
    """Download real de uma faixa curta; valida arquivo e tags ID3."""
    import imageio_ffmpeg
    from mutagen.id3 import ID3

    staging = os.path.join(tempfile.gettempdir(), "ipodmgr_test_dl")
    downloader = Downloader(
        ffmpeg_path=imageio_ffmpeg.get_ffmpeg_exe(),
        staging_dir=staging,
    )
    # "Me at the zoo" (~19 s) — primeiro vídeo do YouTube, curto e estável.
    track = YTTrack(
        video_id="jNQXAC9IVRw",
        title="Me at the zoo",
        artist="jawed",
        album="",
        duration_s=19,
        thumbnail_url="https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg",
    )
    try:
        path = downloader.download_track(track)
    except Exception as exc:
        pytest.skip(f"download real falhou (rede/yt-dlp): {exc}")

    assert os.path.isfile(path)
    assert path.lower().endswith(".mp3")
    assert os.path.getsize(path) > 100 * 1024
    tags = ID3(path)
    assert tags.get("TIT2") is not None
    assert tags.get("TIT2").text[0] == "Me at the zoo"
    assert tags.get("TPE1") is not None
