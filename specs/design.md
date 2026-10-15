# Design — iPod Manager

## Arquitetura

```
main.py                     # entry point: python main.py
ipod_manager/
├── __init__.py
├── ipod_service.py         # MÓDULO 1 — wrapper pygpod (agente 1)
├── downloader.py           # MÓDULO 2 — YouTube Music (agente 2)
└── gui/
    ├── __init__.py
    ├── app.py              # MÓDULO 3 — MainWindow PySide6 (agente 3)
    └── workers.py          # QThread workers (agente 3)
specs/                      # este conjunto de documentos
tests/
requirements.txt
```

Princípio: módulos 1 e 2 não conhecem Qt; GUI só fala com eles via os contratos
abaixo. Comunicação GUI↔serviços por signals de `QThread`/`QObject`.

## Decisões técnicas

| Decisão | Escolha | Motivo |
|---|---|---|
| iTunesDB | `pygpod` 0.0.6 | Python puro, validado no iPod real (Nano 1G, HASH58); API `Database` de alto nível |
| GUI | PySide6 6.12 | Nativa, moderna, já instalada |
| Busca/listagem YT Music | `ytmusicapi` | Metadados estruturados sem scraping |
| Download | `yt-dlp` (API Python) | Robusto; videoId → watch URL |
| Conversão MP3 | ffmpeg via `imageio-ffmpeg` | Binário bundled, sem instalação/admin |
| Tags/artwork | `mutagen` | ID3v2 + APIC (capa) |

## Contratos dos módulos (API — obrigatório seguir à risca)

### `ipod_manager/ipod_service.py`

```python
@dataclass
class DeviceInfo:
    name: str          # ex. "iPod Nano 1st Gen (2GB)"
    mountpoint: str    # ex. "I:\\"
    capacity_bytes: int
    free_bytes: int
    track_count: int
    playlist_count: int

@dataclass
class TrackInfo:
    track_id: int      # pygpod track_id (chave estável na sessão)
    title: str
    artist: str
    album: str
    genre: str
    year: int
    track_number: int
    duration_ms: int
    rating: int        # 0–100 (0,20,40,60,80,100)
    play_count: int
    ipod_path: str

@dataclass
class PlaylistInfo:
    playlist_id: int
    name: str
    track_count: int
    is_master: bool
    is_podcast: bool

class IPodService:
    def __init__(self, mountpoint: str) -> None
    # carrega Database.from_file(mountpoint); raises IPodError se falhar

    @staticmethod
    def detect_ipods() -> list[str]        # unidades com iPod_Control (ex. ["I:\\"])
    def device_info(self) -> DeviceInfo
    def list_tracks(self) -> list[TrackInfo]
    def list_playlists(self) -> list[PlaylistInfo]
    def playlist_tracks(self, playlist_id: int) -> list[TrackInfo]

    # mutações — alteram o modelo em memória; nada grava até save()
    def update_track(self, track_id: int, **fields) -> None
        # fields ⊆ {title, artist, album, genre, year, track_number, rating}
    def add_files(self, paths: list[str]) -> list[int]
        # retorna track_ids novos; falha individual -> coleta em IPodError parcial? NÃO: pula e loga
    def remove_tracks(self, track_ids: list[int]) -> None   # apaga arquivo também
    def export_tracks(self, track_ids: list[int], dest_dir: str) -> list[str]
    def create_playlist(self, name: str) -> int             # retorna playlist_id
    def rename_playlist(self, playlist_id: int, name: str) -> None
    def delete_playlist(self, playlist_id: int) -> None
    def add_to_playlist(self, playlist_id: int, track_ids: list[int]) -> None
    def remove_from_playlist(self, playlist_id: int, track_ids: list[int]) -> None

    @property
    def dirty(self) -> bool
    def save(self, backup: bool = True) -> None
        # backup=True: copia iPod_Control\iTunes para iPod_Control\iTunes.backup-<ts>
        # antes de Database.save(); rollback se save falhar
    def eject(self) -> None                 # save() + flush
```

Erros: exceção `IPodError(Exception)` no módulo; envolver falhas pygpod.

Notas de implementação (pygpod):
- `from pygpod.model.database import Database`; `db = Database("I:\\")` (o construtor carrega do mountpoint; `Database.from_file` só parseia um arquivo iTunesDB avulso, sem mountpoint/dispositivo).
- `db.add_track(path, **meta)` copia p/ `iPod_Control\Music\Fxx` e lê tags mutagen.
- `db.remove_track(track, delete_file=True)`; `db.save()` grava DB + checksum.
- `db.create_playlist(name)`, `db.delete_playlist(pl)`, `add/remove_track_to_playlist`.
- `Track` expõe .title .artist .album .genre .year .track_number .duration_ms? —
  usar `duration` (ms) e `rating` (0–100); `track_id` e `dbid` existem.
- Detecção de unidades: iterar letras via `ctypes.windll.kernel32.GetLogicalDrives`
  ou `psutil.disk_partitions()` (se psutil faltar, fallback ctypes) procurando
  `<drive>\iPod_Control`.

### `ipod_manager/downloader.py`

```python
@dataclass
class YTTrack:
    video_id: str
    title: str
    artist: str
    album: str
    duration_s: int
    thumbnail_url: str | None

class YTMusicClient:
    def __init__(self) -> None             # ytmusicapi.YTMusic() sem auth
    def search(self, query: str, limit: int = 20) -> list[YTTrack]
        # ytm.search(query, filter="songs", limit=limit)
    def playlist_tracks(self, url_or_id: str) -> tuple[str, list[YTTrack]]
        # retorna (nome_da_playlist, faixas); aceita URL completa ou id
        # extrai id com regex r"list=([\w-]+)" se vier URL

class Downloader:
    def __init__(self, ffmpeg_path: str, staging_dir: str) -> None
    def download_track(
        self, track: YTTrack,
        progress_cb: Callable[[str, int], None] | None = None,  # (video_id, 0-100)
    ) -> str
        # yt-dlp: url=f"https://music.youtube.com/watch?v={video_id}"
        # postprocessor FFmpegExtractAudio mp3 192k; out: staging_dir/{artist} - {title}.mp3 (sanitizado)
        # depois: mutagen grava TIT2/TPE1/TALB + APIC (thumbnail, se der p/ baixar)
        # retorna path do mp3; raises DownloadError
    def download_playlist(
        self, tracks: list[YTTrack],
        progress_cb: Callable[[int, int, str], None] | None = None,  # (done, total, msg)
    ) -> list[str]
        # continua nas falhas; retorna paths OK
```

Erros: `DownloadError(Exception)`.

## GUI (`gui/app.py` + `gui/workers.py`)

Janela única `MainWindow`, título "iPod Manager", ~1200×700, pt-BR:

- **Toolbar**: combo de unidade + botão "Detectar iPod" | "Adicionar arquivos" |
  "Remover" | "Exportar" | espaço livre | "Salvar no iPod" (habilitado se dirty) |
  "Ejetar".
- **Esquerda** (`QTreeWidget`/lista): playlists do iPod; clique filtra a tabela;
  menu de contexto: nova/renomear/excluir; botão "+" cria playlist.
- **Centro** (`QTableWidget`): colunas Título, Artista, Álbum, Gênero, Ano, Nº,
  Duração, ★; edição inline (`DoubleClicked`/delegates); filtro `QLineEdit`;
  seleção múltipla; menu contexto: adicionar à playlist →, remover do iPod,
  exportar; aceita drag-and-drop de arquivos.
- **Direita (aba "YouTube Music")**: campo de busca + lista de resultados
  (checkboxes); campo URL de playlist + "Carregar playlist"; lista de faixas da
  playlist; botões "Baixar selecionadas" / "Baixar todas" / "Baixar playlist p/
  iPod"; fila de download com `QProgressBar` por item; opção "enviar direto ao
  iPod" (default) vs só staging.
- **Status bar**: mensagens + progresso global.

`workers.py` (QObject + QThread, moveToThread):
- `LoadWorker(service)` → sinais `loaded(device_info, tracks, playlists)`, `error`
- `SaveWorker(service)` → `saved()`, `error`
- `DownloadWorker(downloader, tracks, service|None, playlist_name|None)` →
  `item_done(idx, path)`, `item_failed(idx, err)`, `all_done(paths)`, `progress`

Regras GUI:
- Todo `update_track/add/remove` marca dirty e atualiza botão Salvar.
- Remover pede `QMessageBox.question` com contagem.
- Downloads direto ao iPod: ao fim de cada arquivo, `service.add_files([path])`
  (thread do worker; acesso ao service é sequencial — a GUI fica bloqueada p/
  mutações durante worker ativo) e, se `playlist_name`, cria playlist (uma vez)
  e `add_to_playlist`.
- Config `%APPDATA%\iPodManager\config.json`: `{"staging_dir": ..., "last_mount": "I:\\"}`.
- Staging default: `%LOCALAPPDATA%\iPodManager\staging`.

## requirements.txt

```
pygpod==0.0.6
ytmusicapi
yt-dlp
mutagen
Pillow
imageio-ffmpeg
PySide6
pyusb
libusb-package
```

## Riscos / mitigações

- Escrita corromper DB → backup automático de `iPod_Control\iTunes` antes de
  cada `save()` + rollback.
- Nano 1G sem suporte a capa colorida → pygpod ignora artwork se geração não
  suporta (a geração suporta sim ithmb; pygpod trata).
- yt-dlp quebrar por mudança do YouTube → erros por faixa, não abortam lote.
- `save()` destrutivo → primeiro teste de escrita real feito manualmente com
  backup prévio (T6 em tasks.md).
