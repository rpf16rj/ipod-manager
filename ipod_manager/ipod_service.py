"""Serviço de alto nível para gerenciar um iPod clássico via pygpod.

Este módulo encapsula a biblioteca ``pygpod`` expondo uma API simples e
estável para a GUI: listar faixas/playlists, editar metadados, enviar e
remover arquivos, gerenciar playlists e gravar o iTunesDB com backup
automático e rollback.

Todas as mutações acontecem apenas no modelo em memória; nada é gravado
no iPod até que :meth:`IPodService.save` seja chamado explicitamente.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pygpod.model.database import Database
from pygpod.model.playlist import Playlist
from pygpod.model.track import Track
from pygpod.utils.encoding import ipod_path_to_os

logger = logging.getLogger(__name__)


class IPodError(Exception):
    """Erro em operações do iPod; envolve falhas do pygpod e de I/O."""


@dataclass
class DeviceInfo:
    """Informações gerais do dispositivo conectado."""

    name: str          # ex. "iPod Nano 1st Gen (2GB)"
    mountpoint: str    # ex. "I:\\"
    capacity_bytes: int
    free_bytes: int
    track_count: int
    playlist_count: int


@dataclass
class TrackInfo:
    """Metadados de uma faixa do iPod."""

    track_id: int      # track_id do pygpod (chave estável na sessão)
    title: str
    artist: str
    album: str
    genre: str
    year: int
    track_number: int
    duration_ms: int
    rating: int        # 0-100 (0,20,40,60,80,100)
    play_count: int
    size_bytes: int
    added_ts: int      # epoch (s) de quando entrou na biblioteca; 0 se n/d
    ipod_path: str


@dataclass
class PlaylistInfo:
    """Metadados de uma playlist do iPod."""

    playlist_id: int
    name: str
    track_count: int
    is_master: bool
    is_podcast: bool


# Caracteres inválidos em nomes de arquivo no Windows.
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


class IPodService:
    """Fachada de alto nível sobre :class:`pygpod.model.database.Database`.

    Args:
        mountpoint: Ponto de montagem do iPod (ex. ``"I:\\\\"``).

    Raises:
        IPodError: Se o iTunesDB não puder ser carregado.
    """

    #: Campos editáveis aceitos por :meth:`update_track`.
    _EDITABLE_FIELDS = frozenset(
        {"title", "artist", "album", "genre", "year", "track_number", "rating"}
    )

    def __init__(self, mountpoint: str) -> None:
        self.mountpoint: str = os.path.normpath(str(mountpoint))
        #: Mensagens das falhas individuais do último lote (add/remove/export).
        self.last_errors: list[str] = []
        self._dirty = False
        try:
            # Database(mountpoint) carrega iPod_Control/iTunes/iTunesDB,
            # detecta o modelo e prepara o checksum (ex.: HASH58).
            self._db = Database(self.mountpoint)
        except Exception as exc:
            raise IPodError(
                f"Não foi possível abrir o iPod em '{mountpoint}': {exc}"
            ) from exc
        logger.info(
            "iPod aberto em %s: %d faixas, %d playlists",
            self.mountpoint,
            len(self._db.tracks),
            len(self._db.playlists),
        )

    # ------------------------------------------------------------------
    # Detecção de dispositivos
    # ------------------------------------------------------------------

    @staticmethod
    def detect_ipods() -> list[str]:
        """Retorna unidades que contêm ``iPod_Control`` (ex. ``["I:\\\\"]``).

        Varre todas as letras de unidade presentes (removíveis e fixas —
        iPods modificados podem aparecer como disco fixo).
        """
        encontrados: list[str] = []
        for letra in IPodService._drive_letters():
            raiz = f"{letra}:\\"
            try:
                if os.path.isdir(os.path.join(raiz, "iPod_Control")):
                    encontrados.append(raiz)
            except OSError:
                continue
        logger.debug("iPods detectados: %s", encontrados)
        return encontrados

    @staticmethod
    def _drive_letters() -> list[str]:
        """Letras de unidades presentes via ``GetLogicalDrives``.

        Fallback: todas as letras A-Z (ou /media, /mnt em não-Windows).
        """
        if sys.platform == "win32":
            try:
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                return [chr(ord("A") + i) for i in range(26) if bitmask & (1 << i)]
            except Exception:
                logger.debug("GetLogicalDrives falhou; varrendo A-Z", exc_info=True)
        return [chr(c) for c in range(ord("A"), ord("Z") + 1)]

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def device_info(self) -> DeviceInfo:
        """Retorna informações do dispositivo (modelo, espaço, totais)."""
        try:
            usage = shutil.disk_usage(self.mountpoint)
        except OSError as exc:
            raise IPodError(
                f"Falha ao obter espaço em disco de '{self.mountpoint}': {exc}"
            ) from exc
        name = "iPod"
        if self._db.device is not None:
            try:
                name = self._db.device.model or name
            except Exception:
                logger.debug("Falha ao obter modelo do dispositivo", exc_info=True)
        return DeviceInfo(
            name=name,
            mountpoint=self.mountpoint,
            capacity_bytes=usage.total,
            free_bytes=usage.free,
            track_count=len(self._db.tracks),
            playlist_count=len(self._db.playlists),
        )

    def list_tracks(self) -> list[TrackInfo]:
        """Lista todas as faixas do iPod."""
        return [self._to_track_info(t) for t in self._db.tracks]

    def list_playlists(self) -> list[PlaylistInfo]:
        """Lista todas as playlists, incluindo master/podcast.

        A GUI deve filtrar por ``is_master``/``is_podcast`` conforme
        necessário.
        """
        return [
            PlaylistInfo(
                playlist_id=pl.playlist_id,
                name=pl.name,
                track_count=pl.track_count,
                is_master=pl.is_master,
                is_podcast=pl.is_podcast,
            )
            for pl in self._db.playlists
        ]

    def playlist_tracks(self, playlist_id: int) -> list[TrackInfo]:
        """Retorna as faixas de uma playlist, na ordem da playlist."""
        playlist = self._get_playlist(playlist_id)
        return [self._to_track_info(t) for t in playlist.tracks]

    def playlists_by_track(self) -> dict[int, list[str]]:
        """Mapeia ``track_id`` → nomes das playlists que contêm a faixa.

        Playlists master/podcast são ignoradas (a master contém todas).
        Usado pela GUI para a coluna "Playlists" da biblioteca.
        """
        mapa: dict[int, list[str]] = {}
        for pl in self._db.playlists:
            if pl.is_master or pl.is_podcast:
                continue
            for tid in pl.track_ids:
                mapa.setdefault(int(tid), []).append(pl.name or "")
        return mapa

    # ------------------------------------------------------------------
    # Mutações (modelo em memória; gravar exige save())
    # ------------------------------------------------------------------

    def update_track(self, track_id: int, **fields) -> None:
        """Atualiza metadados de uma faixa.

        Args:
            track_id: ID da faixa (``TrackInfo.track_id``).
            fields: Subconjunto de ``{title, artist, album, genre, year,
                track_number, rating}``.

        Raises:
            IPodError: Faixa inexistente ou campo não editável.
        """
        track = self._get_track(track_id)
        invalidos = set(fields) - self._EDITABLE_FIELDS
        if invalidos:
            raise IPodError(
                f"Campos não editáveis: {sorted(invalidos)}. "
                f"Permitidos: {sorted(self._EDITABLE_FIELDS)}"
            )
        # Os setters de Track propagam a alteração ao record MHIT
        # (MHODs de texto e campos do cabeçalho), que é serializado
        # integralmente por db.save().
        for nome, valor in fields.items():
            try:
                setattr(track, nome, valor)
            except Exception as exc:
                raise IPodError(
                    f"Falha ao atualizar '{nome}' da faixa {track_id}: {exc}"
                ) from exc
        if fields:
            self._dirty = True

    def add_files(
        self,
        paths: list[str],
        ffmpeg_path: str | None = None,
        progress_cb=None,
    ) -> list[int]:
        """Copia arquivos de áudio locais para o iPod.

        Arquivos em formatos que o iPod não toca (FLAC, OGG, Opus, WMA,
        APE, WebM, MKA) são convertidos automaticamente para MP3 192 kbps
        quando ``ffmpeg_path`` aponta para um binário ffmpeg válido; sem
        ele, a falha é reportada em :attr:`last_errors`.

        Falhas individuais são logadas e coletadas em
        :attr:`last_errors` sem abortar o lote.

        ``progress_cb(done, total, nome)`` (opcional) é chamado antes de
        cada arquivo e ao final com ``(total, total, "")``.

        Returns:
            Lista de ``track_id`` das faixas adicionadas com sucesso.
        """
        from pygpod.exceptions import UnsupportedFormatError
        from pygpod.tags import check_format_supported

        # Pré-check de espaço: evita lotes que enchem o disco no meio.
        total_bytes = 0
        for p in paths:
            try:
                total_bytes += os.path.getsize(p)
            except OSError:
                pass
        livre = shutil.disk_usage(self.mountpoint).free
        # Margem: ~2 MB para regravar iTunesDB + folga de filesystem.
        if total_bytes > max(0, livre - 2 * 1024 * 1024):
            raise IPodError(
                "Espaço insuficiente no iPod: "
                f"{total_bytes / 2**20:.0f} MB necessários, "
                f"{livre / 2**20:.0f} MB livres. "
                "Remova músicas ou use 'Limpar arquivos órfãos'."
            )

        novos_ids: list[int] = []
        self.last_errors = []
        total = len(paths)
        for i, path in enumerate(paths):
            if progress_cb is not None:
                try:
                    progress_cb(i, total, os.path.basename(str(path)))
                except Exception:  # noqa: BLE001 — cb nunca aborta o lote
                    pass
            origem = str(path)
            convertido: str | None = None
            try:
                try:
                    check_format_supported(origem)
                except UnsupportedFormatError:
                    if not ffmpeg_path:
                        raise
                    convertido = self._convert_to_mp3(origem, ffmpeg_path)
                    origem = convertido
                track = self._db.add_track(origem)
                novos_ids.append(track.track_id)
            except Exception as exc:
                msg = f"Falha ao adicionar '{path}': {exc}"
                logger.error(msg)
                self.last_errors.append(msg)
            finally:
                if convertido:
                    try:
                        os.unlink(convertido)
                    except OSError:
                        pass
        if progress_cb is not None:
            try:
                progress_cb(total, total, "")
            except Exception:  # noqa: BLE001
                pass
        if novos_ids:
            self._dirty = True
        logger.info(
            "add_files: %d adicionados, %d falhas", len(novos_ids), len(self.last_errors)
        )
        return novos_ids

    @staticmethod
    def _convert_to_mp3(src: str, ffmpeg_path: str) -> str:
        """Converte ``src`` para MP3 192 kbps num arquivo temporário.

        Preserva as tags do original (``-map_metadata 0``) e grava
        ID3v2.3 para compatibilidade com iPods antigos.
        """
        dest = os.path.join(
            tempfile.gettempdir(),
            f"ipodmgr_conv_{os.getpid()}_{abs(hash(src)) & 0xFFFFFF:x}.mp3",
        )
        cmd = [
            ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
            "-i", src, "-vn", "-map_metadata", "0",
            "-codec:a", "libmp3lame", "-b:a", "192k",
            "-id3v2_version", "3", dest,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IPodError(
                f"Falha ao converter '{os.path.basename(src)}' para MP3: {exc}"
            ) from exc
        if proc.returncode != 0 or not os.path.isfile(dest):
            raise IPodError(
                f"Falha ao converter '{os.path.basename(src)}' para MP3: "
                f"{(proc.stderr or '').strip()[-300:]}"
            )
        return dest

    def remove_tracks(self, track_ids: list[int], progress_cb=None) -> None:
        """Remove faixas do iTunesDB e apaga os arquivos em iPod_Control\\Music.

        Falhas individuais são coletadas em :attr:`last_errors`.
        ``progress_cb(done, total, nome)`` opcional, mesma semântica de
        :meth:`add_files`.
        """
        self.last_errors = []
        removidas = 0
        total = len(track_ids)
        for i, tid in enumerate(track_ids):
            if progress_cb is not None:
                try:
                    track = self._db.get_track(tid)
                    nome = (
                        f"{track.artist} - {track.title}"
                        if track is not None else str(tid)
                    )
                    progress_cb(i, total, nome)
                except Exception:  # noqa: BLE001
                    pass
            track = self._db.get_track(tid)
            if track is None:
                msg = f"Faixa {tid} não encontrada no banco de dados"
                logger.warning(msg)
                self.last_errors.append(msg)
                continue
            try:
                self._db.remove_track(track, delete_file=True)
                removidas += 1
            except Exception as exc:
                msg = f"Falha ao remover a faixa {tid}: {exc}"
                logger.error(msg)
                self.last_errors.append(msg)
        if progress_cb is not None:
            try:
                progress_cb(total, total, "")
            except Exception:  # noqa: BLE001
                pass
        if removidas:
            self._dirty = True

    def export_tracks(
        self, track_ids: list[int], dest_dir: str, progress_cb=None
    ) -> list[str]:
        """Copia os arquivos físicos das faixas do iPod para ``dest_dir``.

        Os arquivos são nomeados como ``"Artista - Título.ext"`` (com
        sanitização dos caracteres inválidos no Windows).

        Returns:
            Lista de caminhos dos arquivos exportados.
        """
        dest = Path(dest_dir)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise IPodError(f"Não foi possível criar '{dest_dir}': {exc}") from exc

        exportados: list[str] = []
        self.last_errors = []
        total = len(track_ids)
        for i, tid in enumerate(track_ids):
            track = self._db.get_track(tid)
            if progress_cb is not None:
                try:
                    nome = (
                        f"{track.artist} - {track.title}"
                        if track is not None else str(tid)
                    )
                    progress_cb(i, total, nome)
                except Exception:  # noqa: BLE001
                    pass
            if track is None:
                msg = f"Faixa {tid} não encontrada no banco de dados"
                logger.warning(msg)
                self.last_errors.append(msg)
                continue
            src = Path(ipod_path_to_os(track.ipod_path, self.mountpoint))
            if not src.is_file():
                msg = f"Arquivo da faixa {tid} não existe no iPod: {src}"
                logger.warning(msg)
                self.last_errors.append(msg)
                continue
            alvo = self._unique_path(dest / self._export_filename(track, src))
            try:
                shutil.copy2(src, alvo)
                exportados.append(str(alvo))
            except OSError as exc:
                msg = f"Falha ao exportar a faixa {tid} para '{alvo}': {exc}"
                logger.error(msg)
                self.last_errors.append(msg)
        if progress_cb is not None:
            try:
                progress_cb(total, total, "")
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "export_tracks: %d exportados, %d falhas",
            len(exportados),
            len(self.last_errors),
        )
        return exportados

    # ---- Playlists ----

    def create_playlist(self, name: str) -> int:
        """Cria uma playlist no iPod e retorna seu ``playlist_id``."""
        if not name or not name.strip():
            raise IPodError("O nome da playlist não pode ser vazio")
        try:
            playlist = self._db.create_playlist(name.strip())
        except Exception as exc:
            raise IPodError(f"Falha ao criar a playlist '{name}': {exc}") from exc
        self._dirty = True
        logger.info("Playlist criada: %r (id=%d)", name, playlist.playlist_id)
        return playlist.playlist_id

    def rename_playlist(self, playlist_id: int, name: str) -> None:
        """Renomeia uma playlist existente."""
        playlist = self._get_playlist(playlist_id)
        if not name or not name.strip():
            raise IPodError("O nome da playlist não pode ser vazio")
        playlist.name = name.strip()
        self._dirty = True

    def delete_playlist(self, playlist_id: int) -> None:
        """Exclui uma playlist (as faixas permanecem na biblioteca)."""
        playlist = self._get_playlist(playlist_id)
        try:
            self._db.delete_playlist(playlist)
        except Exception as exc:
            raise IPodError(
                f"Falha ao excluir a playlist {playlist_id}: {exc}"
            ) from exc
        self._dirty = True

    def add_to_playlist(self, playlist_id: int, track_ids: list[int]) -> None:
        """Adiciona faixas a uma playlist (ignora duplicatas)."""
        playlist = self._get_playlist(playlist_id)
        existentes = set(playlist.track_ids)
        adicionadas = 0
        for tid in track_ids:
            if tid in existentes:
                continue
            track = self._get_track(tid)
            self._db.add_track_to_playlist(playlist, track)
            existentes.add(tid)
            adicionadas += 1
        if adicionadas:
            self._dirty = True

    def remove_from_playlist(self, playlist_id: int, track_ids: list[int]) -> None:
        """Remove faixas de uma playlist (sem apagar da biblioteca)."""
        playlist = self._get_playlist(playlist_id)
        removidas = 0
        for tid in track_ids:
            track = self._db.get_track(tid)
            if track is None:
                logger.warning("Faixa %d não encontrada ao remover da playlist", tid)
                continue
            self._db.remove_track_from_playlist(playlist, track)
            removidas += 1
        if removidas:
            self._dirty = True

    # ------------------------------------------------------------------
    # Manutenção — arquivos órfãos
    # ------------------------------------------------------------------

    def find_orphans(self) -> tuple[list[str], int]:
        """Arquivos em ``iPod_Control\\Music`` sem entrada no iTunesDB.

        Surgem quando faixas são copiadas mas o banco não é salvo (o app
        foi fechado sem "Salvar no iPod", ou o disco encheu no meio).

        Returns:
            ``(paths_absolutos, total_em_bytes)``.
        """
        refs = {
            os.path.normcase(
                os.path.normpath(
                    ipod_path_to_os(t.ipod_path, self.mountpoint)
                )
            )
            for t in self._db.tracks
            if t.ipod_path
        }
        music_dir = os.path.join(self.mountpoint, "iPod_Control", "Music")
        orphans: list[str] = []
        total = 0
        if not os.path.isdir(music_dir):
            return orphans, total
        for root, _dirs, files in os.walk(music_dir):
            for name in files:
                path = os.path.join(root, name)
                if os.path.normcase(os.path.normpath(path)) not in refs:
                    orphans.append(path)
                    try:
                        total += os.path.getsize(path)
                    except OSError:
                        pass
        return orphans, total

    def remove_orphans(self) -> int:
        """Apaga os arquivos órfãos de ``iPod_Control\\Music``.

        Returns:
            Bytes liberados.
        """
        orphans, total = self.find_orphans()
        for path in orphans:
            try:
                os.unlink(path)
            except OSError as exc:
                logger.warning("Falha ao apagar órfão '%s': %s", path, exc)
        logger.info(
            "Órfãos removidos: %d arquivos, %.1f MB",
            len(orphans), total / 2**20,
        )
        return total

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    @property
    def dirty(self) -> bool:
        """``True`` se houve mutação desde o último ``save()``/carga."""
        # db._modified também cobre play counts mesclados na carga.
        return self._dirty or bool(getattr(self._db, "_modified", False))

    def save(self, backup: bool = True) -> None:
        """Grava o iTunesDB no iPod (com checksum do dispositivo).

        Com ``backup=True`` (padrão), copia antes todo o diretório
        ``iPod_Control\\iTunes`` para ``iPod_Control\\iTunes.backup-<ts>``.
        Se a gravação falhar, tenta restaurar o backup (rollback
        best-effort) e relança :class:`IPodError`.

        Raises:
            IPodError: Em falha de backup ou de gravação.
        """
        itunes_dir = Path(self.mountpoint) / "iPod_Control" / "iTunes"
        backup_dir: Path | None = None
        if backup:
            if not itunes_dir.is_dir():
                raise IPodError(
                    f"Diretório do iTunesDB não encontrado: {itunes_dir}"
                )
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir = itunes_dir.with_name(f"iTunes.backup-{stamp}")
            # Saves consecutivos no mesmo segundo colidiriam no nome.
            for n in range(2, 100):
                if not backup_dir.exists():
                    break
                backup_dir = itunes_dir.with_name(
                    f"iTunes.backup-{stamp}-{n}"
                )
            else:
                raise IPodError(
                    "Excesso de backups de iTunes no dispositivo; "
                    "remova os diretórios 'iTunes.backup-*' mais antigos"
                )
            try:
                shutil.copytree(itunes_dir, backup_dir)
            except OSError as exc:
                raise IPodError(
                    f"Falha ao criar backup em '{backup_dir}': {exc}"
                ) from exc
            logger.info("Backup do iTunesDB criado em %s", backup_dir)
        try:
            self._db.save()
        except Exception as exc:
            logger.error("Falha ao gravar o iTunesDB: %s", exc)
            if backup_dir is not None:
                self._restore_backup(backup_dir, itunes_dir)
            raise IPodError(
                f"Falha ao gravar o banco de dados no iPod: {exc}"
            ) from exc
        self._dirty = False
        logger.info("iTunesDB gravado com sucesso em %s", self.mountpoint)

    def eject(self) -> None:
        """Salva alterações pendentes e prepara a remoção segura do iPod."""
        if self.dirty:
            self.save()
        logger.info(
            "iPod em %s salvo; o dispositivo pode ser removido com segurança",
            self.mountpoint,
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _get_track(self, track_id: int) -> Track:
        """Retorna o :class:`Track` ou lança :class:`IPodError`."""
        track = self._db.get_track(track_id)
        if track is None:
            raise IPodError(f"Faixa {track_id} não encontrada")
        return track

    def _get_playlist(self, playlist_id: int) -> Playlist:
        """Retorna a :class:`Playlist` ou lança :class:`IPodError`."""
        for pl in self._db.playlists:
            if pl.playlist_id == playlist_id:
                return pl
        raise IPodError(f"Playlist {playlist_id} não encontrada")

    @staticmethod
    def _to_track_info(track: Track) -> TrackInfo:
        """Converte um :class:`Track` do pygpod em :class:`TrackInfo`."""
        return TrackInfo(
            track_id=int(track.track_id),
            title=track.title or "",
            artist=track.artist or "",
            album=track.album or "",
            genre=track.genre or "",
            year=int(track.year or 0),
            track_number=int(track.track_number or 0),
            duration_ms=int(track.duration_ms or 0),
            rating=int(track.rating or 0),
            play_count=int(track.play_count or 0),
            size_bytes=int(track.file_size or 0),
            added_ts=IPodService._ts(track.time_added),
            ipod_path=track.ipod_path or "",
        )

    @staticmethod
    def _ts(dt) -> int:
        """datetime → epoch (s), tolerando None/naive."""
        if dt is None:
            return 0
        try:
            return int(dt.timestamp())
        except (OSError, OverflowError, ValueError):
            return 0

    @staticmethod
    def _export_filename(track: Track, src: Path) -> str:
        """Monta ``"Artista - Título.ext"`` sanitizado para exportação."""
        artist = track.artist or "Artista Desconhecido"
        title = track.title or src.stem or str(track.track_id)
        nome = _INVALID_FILENAME_CHARS.sub("_", f"{artist} - {title}")
        # Windows não aceita nomes terminados em ponto/espaço.
        nome = nome.rstrip(" .") or str(track.track_id)
        return f"{nome[:150]}{src.suffix.lower()}"

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """Resolve colisões anexando ``" (n)"`` antes da extensão."""
        if not path.exists():
            return path
        for n in range(2, 1000):
            candidato = path.with_name(f"{path.stem} ({n}){path.suffix}")
            if not candidato.exists():
                return candidato
        raise IPodError(f"Não foi possível gerar nome único para '{path.name}'")

    @staticmethod
    def _restore_backup(backup_dir: Path, itunes_dir: Path) -> None:
        """Rollback best-effort: restaura ``iPod_Control\\iTunes`` do backup."""
        try:
            shutil.rmtree(itunes_dir)
            shutil.copytree(backup_dir, itunes_dir)
            logger.info("Backup restaurado a partir de %s", backup_dir)
        except OSError:
            logger.critical(
                "Rollback falhou; o backup permanece em %s para restauração manual",
                backup_dir,
                exc_info=True,
            )
