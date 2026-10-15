"""Workers em QThread para as operações longas do iPod Manager.

Padrão adotado: cada worker é um ``QObject`` movido para uma ``QThread``
(``moveToThread``). A GUI dispara ``run()`` via ``thread.started`` e recebe
os resultados pelos signals. Todos emitem ``finished`` ao final (sucesso ou
erro) para permitir o encerramento limpo da thread.

Os workers recebem as instâncias/classes dos serviços por injeção de
dependência — este módulo não importa ``ipod_service`` nem ``downloader``,
o que o mantém testável isoladamente.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

logger = logging.getLogger(__name__)


class _BaseWorker(QObject):
    """Base com os signals comuns a todos os workers."""

    finished = Signal()
    error = Signal(str)

    def _emit_error(self, exc: BaseException | str) -> None:
        msg = str(exc) if str(exc) else exc.__class__.__name__
        logger.error("%s: %s", self.__class__.__name__, msg)
        self.error.emit(msg)


class LoadWorker(_BaseWorker):
    """Detecta iPods e/ou carrega a biblioteca de um iPod.

    Modos de uso (exclusivos):

    - ``detect_only=True`` + ``service_cls``: chama
      ``service_cls.detect_ipods()`` e emite ``detected``.
    - ``mountpoint`` + ``service_cls``: constrói o serviço na thread do
      worker (``Database.from_file`` é a parte lenta e não pode rodar na
      GUI), emite ``service_ready`` e depois ``loaded``.
    - ``service``: usa a instância já existente (recarga) e emite ``loaded``.
    """

    detected = Signal(list)                  # list[str] — mountpoints
    service_ready = Signal(object)           # IPodService criado na thread
    loaded = Signal(object, list, list)      # DeviceInfo, [TrackInfo], [PlaylistInfo]

    def __init__(
        self,
        service: Any = None,
        mountpoint: str | None = None,
        service_cls: Any = None,
        detect_only: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._mountpoint = mountpoint
        self._service_cls = service_cls
        self._detect_only = detect_only

    @Slot()
    def run(self) -> None:
        try:
            if self._detect_only:
                if self._service_cls is None:
                    raise RuntimeError("service_cls não informado para detecção")
                self.detected.emit(list(self._service_cls.detect_ipods()))
                return

            svc = self._service
            if svc is None:
                if self._service_cls is None or not self._mountpoint:
                    raise RuntimeError("Informe service ou mountpoint+service_cls")
                svc = self._service_cls(self._mountpoint)
                self._service = svc
                self.service_ready.emit(svc)

            info = svc.device_info()
            tracks = svc.list_tracks()
            playlists = svc.list_playlists()
            self.loaded.emit(info, tracks, playlists)
        except Exception as exc:  # noqa: BLE001 — erros viram mensagem na GUI
            self._emit_error(exc)
        finally:
            self.finished.emit()


class SaveWorker(_BaseWorker):
    """Grava o iTunesDB no iPod (``service.save()`` ou ``service.eject()``)."""

    saved = Signal()

    def __init__(self, service: Any, eject: bool = False,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._eject = eject

    @Slot()
    def run(self) -> None:
        try:
            if self._eject:
                self._service.eject()
            else:
                self._service.save()
            self.saved.emit()
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()


class AddFilesWorker(_BaseWorker):
    """Copia arquivos de áudio locais para o iPod (``service.add_files``)."""

    progress = Signal(int, int, str)         # (feitos, total, nome atual)
    added = Signal(list)                     # list[int] — track_ids novos

    def __init__(self, service: Any, paths: list[str],
                 ffmpeg_path: str | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._paths = list(paths)
        self._ffmpeg_path = ffmpeg_path

    @Slot()
    def run(self) -> None:
        try:
            ids = self._service.add_files(
                self._paths,
                ffmpeg_path=self._ffmpeg_path,
                progress_cb=self.progress.emit,
            )
            self.added.emit(list(ids))
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()


class RemoveTracksWorker(_BaseWorker):
    """Remove faixas do iPod (apaga DB + arquivo)."""

    progress = Signal(int, int, str)         # (feitos, total, nome atual)
    removed = Signal(list)                   # list[int] — ids removidos

    def __init__(self, service: Any, track_ids: list[int],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._track_ids = list(track_ids)

    @Slot()
    def run(self) -> None:
        try:
            self._service.remove_tracks(
                self._track_ids, progress_cb=self.progress.emit
            )
            self.removed.emit(self._track_ids)
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()


class ExportWorker(_BaseWorker):
    """Copia faixas do iPod para uma pasta local."""

    progress = Signal(int, int, str)         # (feitos, total, nome atual)
    exported = Signal(list)                  # list[str] — paths gerados

    def __init__(self, service: Any, track_ids: list[int], dest_dir: str,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._track_ids = list(track_ids)
        self._dest_dir = dest_dir

    @Slot()
    def run(self) -> None:
        try:
            paths = self._service.export_tracks(
                self._track_ids, self._dest_dir,
                progress_cb=self.progress.emit,
            )
            self.exported.emit(list(paths))
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()


class OrphanScanWorker(_BaseWorker):
    """Procura arquivos órfãos em iPod_Control\\Music (``find_orphans``)."""

    found = Signal(list, int)                # (paths, total_bytes)

    def __init__(self, service: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service

    @Slot()
    def run(self) -> None:
        try:
            paths, total = self._service.find_orphans()
            self.found.emit(paths, int(total))
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()


class DownloadWorker(_BaseWorker):
    """Baixa faixas do YouTube Music e, opcionalmente, envia ao iPod.

    ``service=None`` → apenas baixa para o staging dir.
    ``service`` + ``playlist_name`` → ao final, cria a playlist homônima no
    iPod (uma única vez) e adiciona as faixas copiadas com sucesso.

    Signals:
    - ``progress(idx, pct)``: progresso 0–100 do item ``idx``.
    - ``item_done(idx, path)``: faixa baixada (e copiada ao iPod, se houver).
    - ``item_failed(idx, err)``: falha no download do item.
    - ``all_done(paths)``: lote concluído (paths baixados com sucesso).
    - ``error``: falhas não fatais (ex.: cópia p/ iPod, criação de playlist).
    """

    progress = Signal(int, int)              # (idx, 0-100)
    item_done = Signal(int, str)             # (idx, path)
    item_failed = Signal(int, str)           # (idx, erro)
    all_done = Signal(list)                  # list[str]

    def __init__(
        self,
        downloader: Any,
        tracks: list[Any],
        service: Any = None,
        playlist_name: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._downloader = downloader
        self._tracks = list(tracks)
        self._service = service
        self._playlist_name = playlist_name
        self._cancelled = False

    @Slot()
    def cancel(self) -> None:
        """Interrompe o lote após a faixa corrente."""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        paths: list[str] = []
        added_ids: list[int] = []
        try:
            for idx, track in enumerate(self._tracks):
                if self._cancelled:
                    break
                try:
                    def _cb(video_id: str, pct: int, _i: int = idx) -> None:
                        self.progress.emit(_i, max(0, min(100, int(pct))))

                    path = self._downloader.download_track(
                        track, progress_cb=_cb
                    )
                except Exception as exc:  # noqa: BLE001 — continua nas demais
                    msg = str(exc) or exc.__class__.__name__
                    logger.warning(
                        "Download falhou (%s): %s",
                        getattr(track, "title", "?"), msg,
                    )
                    self.item_failed.emit(idx, msg)
                    continue

                paths.append(path)

                if self._service is not None:
                    try:
                        new_ids = self._service.add_files([path])
                        added_ids.extend(new_ids)
                    except Exception as exc:  # noqa: BLE001
                        self.error.emit(
                            f"'{getattr(track, 'title', path)}' foi baixada, "
                            f"mas falhou ao copiar para o iPod: {exc}"
                        )
                self.item_done.emit(idx, path)

            if (
                self._service is not None
                and self._playlist_name
                and added_ids
                and not self._cancelled
            ):
                try:
                    # Reutiliza playlist homônima existente (evita duplicata
                    # em retries e re-execuções da mesma playlist).
                    pid = None
                    for pl in self._service.list_playlists():
                        if pl.name == self._playlist_name:
                            pid = pl.playlist_id
                            break
                    if pid is None:
                        pid = self._service.create_playlist(
                            self._playlist_name
                        )
                    self._service.add_to_playlist(pid, added_ids)
                except Exception as exc:  # noqa: BLE001
                    self.error.emit(
                        f"Falha ao criar/atualizar a playlist "
                        f"'{self._playlist_name}' no iPod: {exc}"
                    )

            self.all_done.emit(paths)
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()


class SearchWorker(_BaseWorker):
    """Busca músicas no YouTube Music.

    Se ``client`` for ``None``, constrói um ``client_cls()`` dentro da
    thread (a inicialização pode envolver rede) e o devolve via
    ``client_ready`` para reuso pela GUI.
    """

    results = Signal(list)                   # list[YTTrack]
    client_ready = Signal(object)            # YTMusicClient

    def __init__(
        self,
        query: str,
        client: Any = None,
        client_cls: Callable[[], Any] | None = None,
        limit: int = 20,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._query = query
        self._client = client
        self._client_cls = client_cls
        self._limit = limit

    @Slot()
    def run(self) -> None:
        try:
            client = self._client
            if client is None:
                if self._client_cls is None:
                    raise RuntimeError("client/client_cls não informado")
                client = self._client_cls()
                self.client_ready.emit(client)
            self.results.emit(list(client.search(self._query, self._limit)))
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()


class PlaylistFetchWorker(_BaseWorker):
    """Carrega as faixas de uma playlist pública do YouTube Music."""

    loaded = Signal(str, list)               # (nome_da_playlist, [YTTrack])
    client_ready = Signal(object)            # YTMusicClient

    def __init__(
        self,
        url_or_id: str,
        client: Any = None,
        client_cls: Callable[[], Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._url_or_id = url_or_id
        self._client = client
        self._client_cls = client_cls

    @Slot()
    def run(self) -> None:
        try:
            client = self._client
            if client is None:
                if self._client_cls is None:
                    raise RuntimeError("client/client_cls não informado")
                client = self._client_cls()
                self.client_ready.emit(client)
            name, tracks = client.playlist_tracks(self._url_or_id)
            self.loaded.emit(str(name), list(tracks))
        except Exception as exc:  # noqa: BLE001
            self._emit_error(exc)
        finally:
            self.finished.emit()
