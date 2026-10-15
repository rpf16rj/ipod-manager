"""Downloader — busca e download de faixas do YouTube Music para MP3.

Módulo independente de Qt. Usa ``ytmusicapi`` para metadados (busca e
playlists públicas, sem autenticação) e ``yt-dlp`` para baixar o áudio,
convertendo para MP3 192 kbps via ffmpeg (binário do ``imageio-ffmpeg``).
As tags ID3 (título, artista, álbum e capa) são gravadas com ``mutagen``.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Erro ao buscar, baixar ou converter uma faixa do YouTube Music."""


@dataclass
class YTTrack:
    """Faixa do YouTube Music (resultado de busca ou item de playlist)."""

    video_id: str
    title: str
    artist: str
    album: str
    duration_s: int
    thumbnail_url: str | None


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _sanitize_filename(name: str, limit: int = 120) -> str:
    """Remove caracteres inválidos no Windows e trunca o nome do arquivo."""
    name = _INVALID_FILENAME_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return (name[:limit].rstrip(" .") or "faixa")


def _best_thumbnail(thumbnails: list | None) -> str | None:
    """Retorna a URL da thumbnail de maior resolução disponível."""
    if not thumbnails:
        return None
    best = max(
        (t for t in thumbnails if isinstance(t, dict) and t.get("url")),
        key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
        default=None,
    )
    return best["url"] if best else None


def _track_from_dict(item: dict) -> YTTrack | None:
    """Converte um dict do ytmusicapi em YTTrack; None se indisponível."""
    if not isinstance(item, dict):
        return None
    video_id = item.get("videoId")
    if not video_id or item.get("isAvailable") is False:
        return None

    artists = item.get("artists") or []
    artist = ", ".join(
        a["name"] for a in artists if isinstance(a, dict) and a.get("name")
    ) or "Artista desconhecido"

    album = item.get("album")
    if isinstance(album, dict):
        album_name = album.get("name") or ""
    else:
        album_name = album or ""

    try:
        duration = int(item.get("duration_seconds") or 0)
    except (TypeError, ValueError):
        duration = 0

    return YTTrack(
        video_id=str(video_id),
        title=item.get("title") or "Sem título",
        artist=artist,
        album=album_name,
        duration_s=duration,
        thumbnail_url=_best_thumbnail(item.get("thumbnails")),
    )


# ---------------------------------------------------------------------------
# Cliente YouTube Music (metadados, sem auth)
# ---------------------------------------------------------------------------


class YTMusicClient:
    """Cliente fino sobre ``ytmusicapi.YTMusic`` sem autenticação."""

    def __init__(self) -> None:
        from ytmusicapi import YTMusic

        self._ytm = YTMusic()

    def search(self, query: str, limit: int = 20) -> list[YTTrack]:
        """Busca músicas por texto; retorna lista de YTTrack."""
        try:
            results = self._ytm.search(query, filter="songs", limit=limit)
        except Exception as exc:
            raise DownloadError(f"Falha na busca por '{query}': {exc}") from exc
        return [t for t in (_track_from_dict(i) for i in results or []) if t]

    def playlist_tracks(self, url_or_id: str) -> tuple[str, list[YTTrack]]:
        """Retorna (nome_da_playlist, faixas) de uma playlist pública.

        Aceita URL completa (``music.youtube.com/playlist?list=...``) ou o
        id direto. Faixas indisponíveis (videoId None / isAvailable False)
        são ignoradas.
        """
        match = re.search(r"list=([\w-]+)", url_or_id)
        playlist_id = match.group(1) if match else url_or_id.strip()
        try:
            playlist = self._ytm.get_playlist(playlist_id)
        except Exception as exc:
            raise DownloadError(
                f"Falha ao carregar playlist '{playlist_id}': {exc}"
            ) from exc
        name = playlist.get("title") or "Playlist do YouTube Music"
        tracks = [
            t for t in (_track_from_dict(i) for i in playlist.get("tracks") or [])
            if t
        ]
        return name, tracks


# ---------------------------------------------------------------------------
# Download + conversão + tags
# ---------------------------------------------------------------------------


class Downloader:
    """Baixa faixas do YouTube Music como MP3 192 kbps com tags ID3."""

    def __init__(self, ffmpeg_path: str, staging_dir: str) -> None:
        """``ffmpeg_path``: binário ffmpeg (ou pasta que o contém);
        ``staging_dir``: pasta de destino dos MP3."""
        self.ffmpeg_path = ffmpeg_path
        self.staging_dir = staging_dir
        os.makedirs(staging_dir, exist_ok=True)

    # -- API pública -------------------------------------------------------

    def download_track(
        self,
        track: YTTrack,
        progress_cb: Callable[[str, int], None] | None = None,
    ) -> str:
        """Baixa ``track`` para ``staging_dir/{artist} - {title}.mp3``.

        ``progress_cb`` (opcional) recebe ``(video_id, porcentagem 0-100)``.
        Retorna o caminho do MP3; levanta ``DownloadError`` em falhas.
        """
        from yt_dlp import YoutubeDL

        safe = _sanitize_filename(f"{track.artist} - {track.title}")
        mp3_path = os.path.join(self.staging_dir, f"{safe}.mp3")

        def _progress_hook(d: dict) -> None:
            if progress_cb is None:
                return
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = int(done * 100 / total) if total else 0
                progress_cb(track.video_id, min(pct, 99))
            elif status == "finished":
                progress_cb(track.video_id, 99)

        urls = [
            f"https://music.youtube.com/watch?v={track.video_id}",
            f"https://www.youtube.com/watch?v={track.video_id}",
        ]
        last_exc: Exception | None = None
        baixado = False
        # Tenta primeiro com capa embutida via yt-dlp; se as duas URLs
        # falharem, repete sem thumbnail (robustez contra falha de postproc).
        tentativas = [True, False] if track.thumbnail_url else [False]
        for with_thumb in tentativas:
            for url in urls:
                try:
                    opts = self._ydl_opts(safe, with_thumb, _progress_hook)
                    with YoutubeDL(opts) as ydl:
                        ydl.download([url])
                    baixado = True
                    break
                except Exception as exc:  # yt-dlp usa exceções próprias
                    last_exc = exc
                    logger.warning("yt-dlp falhou em %s: %s", url, exc)
            if baixado:
                break

        if not baixado:
            raise DownloadError(
                f"Falha ao baixar '{track.artist} - {track.title}': {last_exc}"
            )

        mp3_path = self._locate_mp3(safe, mp3_path)
        if mp3_path is None:
            raise DownloadError(
                f"Download concluído mas o MP3 de '{track.title}' não foi "
                f"encontrado em {self.staging_dir}"
            )

        self._write_tags(mp3_path, track)
        if progress_cb is not None:
            progress_cb(track.video_id, 100)
        return mp3_path

    def download_playlist(
        self,
        tracks: list[YTTrack],
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> list[str]:
        """Baixa uma lista de faixas; continua após falhas individuais.

        ``progress_cb`` (opcional) recebe ``(feitas, total, mensagem)`` após
        cada item. Retorna apenas os caminhos baixados com sucesso.
        """
        paths: list[str] = []
        total = len(tracks)
        for idx, track in enumerate(tracks, 1):
            try:
                paths.append(self.download_track(track))
                msg = f"{idx}/{total} — {track.artist} - {track.title}"
            except Exception as exc:
                msg = (
                    f"{idx}/{total} — falha em "
                    f"'{track.artist} - {track.title}': {exc}"
                )
                logger.warning(msg)
            if progress_cb is not None:
                progress_cb(idx, total, msg)
        return paths

    # -- Internos ----------------------------------------------------------

    def _ydl_opts(self, base_name: str, with_thumb: bool, hook) -> dict:
        postprocessors: list[dict] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
        ]
        if with_thumb:
            postprocessors += [
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
                {"key": "EmbedThumbnail"},
            ]
        return {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(self.staging_dir, base_name + ".%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "ffmpeg_location": self.ffmpeg_path,
            "writethumbnail": with_thumb,
            "postprocessors": postprocessors,
            "progress_hooks": [hook],
        }

    def _locate_mp3(self, base_name: str, expected: str) -> str | None:
        """Localiza o MP3 produzido; tolera pequenas diferenças de nome."""
        if os.path.isfile(expected):
            return expected
        candidatos = sorted(
            glob.glob(os.path.join(self.staging_dir, base_name + "*.mp3")),
            key=os.path.getmtime,
            reverse=True,
        )
        return candidatos[0] if candidatos else None

    def _fetch(self, url: str) -> bytes | None:
        """Baixa bytes de uma URL (thumbnail); None em caso de falha."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except Exception as exc:
            logger.warning("Falha ao baixar thumbnail %s: %s", url, exc)
            return None

    def _write_tags(self, mp3_path: str, track: YTTrack) -> None:
        """Grava TIT2/TPE1/TALB e capa APIC (ID3v2.3) no MP3."""
        from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
        from mutagen.id3 import ID3NoHeaderError

        try:
            try:
                tags = ID3(mp3_path)
            except ID3NoHeaderError:
                tags = ID3()

            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=track.title))
            tags.delall("TPE1")
            tags.add(TPE1(encoding=3, text=track.artist))
            if track.album:
                tags.delall("TALB")
                tags.add(TALB(encoding=3, text=track.album))

            if track.thumbnail_url:
                data = self._fetch(track.thumbnail_url)
                if data:
                    mime = (
                        "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
                    )
                    tags.delall("APIC")
                    tags.add(
                        APIC(
                            encoding=3,
                            mime=mime,
                            type=3,  # capa frontal
                            desc="Capa",
                            data=data,
                        )
                    )
            tags.save(mp3_path, v2_version=3)
        except Exception as exc:
            raise DownloadError(
                f"Falha ao gravar tags ID3 em '{mp3_path}': {exc}"
            ) from exc
