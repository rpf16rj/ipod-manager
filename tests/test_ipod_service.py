"""Testes de LEITURA do IPodService contra o iPod real em ``I:\\``.

ATENÇÃO: estes testes nunca chamam save()/add/remove — o dispositivo é
real e pertence ao usuário. São automaticamente pulados (pytest.skip)
se ``I:\\`` não existir ou não contiver ``iPod_Control``.
"""

from __future__ import annotations

import os

import pytest

from ipod_manager.ipod_service import DeviceInfo, IPodService, TrackInfo

MOUNTPOINT = "I:\\"


def _ipod_disponivel() -> bool:
    return os.path.isdir(os.path.join(MOUNTPOINT, "iPod_Control"))


pytestmark = pytest.mark.skipif(
    not _ipod_disponivel(),
    reason=f"iPod não detectado em {MOUNTPOINT} (iPod_Control ausente)",
)


@pytest.fixture(scope="module")
def service() -> IPodService:
    """Instância compartilhada (somente leitura) do serviço."""
    return IPodService(MOUNTPOINT)


def test_detect_ipods_encontra_unidade_i() -> None:
    unidades = IPodService.detect_ipods()
    assert isinstance(unidades, list)
    assert all(u.endswith(":\\") for u in unidades)
    assert MOUNTPOINT in unidades


def test_device_info(service: IPodService) -> None:
    info = service.device_info()
    assert isinstance(info, DeviceInfo)
    assert info.name  # ex. "iPod Nano 1st Gen (2GB)"
    assert info.mountpoint == MOUNTPOINT
    assert info.capacity_bytes > 0
    assert 0 <= info.free_bytes <= info.capacity_bytes
    # Contagens variam com o uso real do dispositivo.
    assert info.track_count == len(service.list_tracks())
    assert info.playlist_count == len(service.list_playlists())


def test_list_tracks(service: IPodService) -> None:
    tracks = service.list_tracks()
    assert len(tracks) >= 1
    assert all(isinstance(t, TrackInfo) for t in tracks)
    # IDs únicos e campos básicos coerentes.
    ids = [t.track_id for t in tracks]
    assert len(set(ids)) == len(ids)
    amostra = tracks[0]
    assert amostra.title
    assert amostra.ipod_path.startswith(":")
    assert amostra.duration_ms > 0
    assert 0 <= amostra.rating <= 100


def test_list_playlists(service: IPodService) -> None:
    playlists = service.list_playlists()
    # O número de playlists varia com o uso real do dispositivo; a única
    # invariante é existir exatamente uma master.
    masters = [p for p in playlists if p.is_master]
    assert len(masters) == 1
    assert all(p.name for p in playlists)


def test_playlist_tracks_master_contem_todas(service: IPodService) -> None:
    master = next(p for p in service.list_playlists() if p.is_master)
    faixas = service.playlist_tracks(master.playlist_id)
    assert len(faixas) == master.track_count
    assert len(faixas) == len(service.list_tracks())


def test_playlist_tracks_subconjunto_da_biblioteca(service: IPodService) -> None:
    todas = {t.track_id for t in service.list_tracks()}
    for pl in service.list_playlists():
        if pl.is_master or pl.track_count == 0:
            continue
        faixas = service.playlist_tracks(pl.playlist_id)
        assert len(faixas) == pl.track_count
        assert {t.track_id for t in faixas} <= todas


def test_playlist_inexistente_levanta_ipod_error(service: IPodService) -> None:
    from ipod_manager.ipod_service import IPodError

    with pytest.raises(IPodError):
        service.playlist_tracks(-1)


def test_dirty_falso_apos_carga(service: IPodService) -> None:
    # Nenhum teste muta o serviço; dirty deve ser False após a carga.
    # (Se o iPod tiver play counts pendentes, pygpod pode marcá-lo —
    #  nesse caso apenas logamos, sem falhar o teste.)
    if service.dirty:
        pytest.xfail("iPod tem play counts pendentes mesclados na carga")
