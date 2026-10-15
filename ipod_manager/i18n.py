"""Internacionalização simples por dicionário (pt / en).

Uso::

    from ipod_manager.i18n import tr, set_lang
    set_lang("en")
    label = QLabel(tr("playlists"))

``tr()`` cai para pt-BR quando a chave falta no idioma ativo, e para a
própria chave se não existir em nenhum — nunca quebra a UI.
"""

from __future__ import annotations

LANG_NAMES = {"pt": "Português (BR)", "en": "English"}
DEFAULT_LANG = "pt"

S: dict[str, dict[str, str]] = {
    "pt": {
        # App / toolbar
        "app_title": "iPod Manager",
        "drive_label": "Unidade:",
        "drive_tip": "Unidade do iPod (detectada automaticamente ou digitada)",
        "no_ipod_short": "Sem iPod",
        "detect": "Detectar iPod",
        "detect_tip": "Procurar unidades com iPod_Control (F5)",
        "add_files": "Adicionar arquivos",
        "add_files_tip": "Copiar arquivos de áudio locais para o iPod",
        "remove": "Remover",
        "remove_tip": "Remover as faixas selecionadas do iPod (Del na tabela)",
        "bulk_edit": "Editar em massa",
        "bulk_edit_tip": "Aplicar artista/álbum/gênero/ano/avaliação a todas as faixas selecionadas",
        "export": "Exportar",
        "export_tip": "Copiar as faixas selecionadas para uma pasta do PC",
        "save": "Salvar no iPod",
        "save_tip": "Gravar alterações no iTunesDB, com backup automático (Ctrl+S)",
        "eject": "Ejetar",
        "eject_tip": "Salvar alterações e preparar o iPod para remoção segura",
        "log": "Log",
        "options": "Opções",
        "language": "Idioma",
        "support": "☕ Apoiar o projeto",
        "about": "Sobre o iPod Manager",
        # Painel de playlists
        "playlists": "Playlists",
        "new_playlist": "+ Nova playlist",
        "new_playlist_tip": "Criar uma playlist no iPod",
        "library": "Biblioteca (todas as músicas)",
        "about_text": "Gerenciador de músicas para iPods clássicos — edite tags, "
            "crie playlists e baixe do YouTube Music, sem iTunes.",
        # Tabela
        "col_title": "Título",
        "col_artist": "Artista",
        "col_album": "Álbum",
        "col_genre": "Gênero",
        "col_year": "Ano",
        "col_num": "Nº",
        "col_dur": "Duração",
        "col_star": "★",
        "col_size": "Tamanho",
        "col_added": "Adicionada",
        "col_playlists": "Playlists",
        "filter_tip": "Filtrar músicas…",
        "drop_tip": "Arraste arquivos de áudio ou faixas aqui",
        # Menus de contexto
        "add_to_playlist": "Adicionar à playlist",
        "remove_from_playlist": "Remover desta playlist",
        "remove_from_ipod": "Remover do iPod",
        "export_tracks": "Exportar…",
        "bulk_edit_menu": "Editar em massa…",
        "rename_playlist": "Renomear…",
        "delete_playlist": "Excluir playlist",
        "new_playlist_menu": "Nova playlist…",
        "playlist_name_prompt": "Nome da playlist:",
        # Painel YouTube Music
        "yt_title": "YouTube Music",
        "search_tip": "Buscar no YouTube Music…",
        "btn_search": "Buscar",
        "url_tip": "Cole a URL de uma playlist pública do YouTube Music",
        "url_label": "Playlist pública (URL ou ID):",
        "btn_load_pl": "Carregar playlist",
        "dl_playlist_tip": "Baixa a playlist carregada e cria uma playlist homônima no iPod",
        "retry_tip": "Baixa novamente apenas as faixas que falharam no último lote",
        "cancel_dl_tip": "Interrompe o lote após a faixa em andamento",
        "log_verbose_tip": "Registra mais detalhes (útil para diagnosticar falhas)",
        "results": "Resultados",
        "playlist_label": "Playlist: —",
        "dl_selected": "Baixar selecionadas",
        "dl_all": "Baixar todas",
        "dl_playlist_ipod": "Baixar playlist p/ iPod",
        "chk_to_ipod": "Enviar direto ao iPod",
        "limit_label": "Máx. por download:",
        "queue": "Fila de downloads",
        "retry_failed": "Repetir falhadas",
        "cancel_dl": "Cancelar downloads",
        # Log dock
        "log_dock": "Log",
        "log_open_file": "Abrir arquivo de log",
        "log_verbose": "Detalhado (DEBUG)",
        "log_clear": "Limpar",
        # Status / mensagens comuns
        "ready": "Pronto",
        "no_ipod": "Nenhum iPod carregado — clique em 'Detectar iPod'",
        "selected_count": "selecionada(s)",
        "saving": "Salvando no iPod…",
        "saved": "Alterações salvas no iPod",
        "lang_restart": "O idioma será aplicado na próxima abertura do app.",
        # Doação
        "donate_title": "☕ Gostando do iPod Manager?",
        "donate_text": "Este app é gratuito e feito com carinho.\n"
            "Se ele te ajudou, considere apoiar o desenvolvimento "
            "com um café — ajuda a manter o projeto vivo!",
        "donate_btn": "☕ Apoiar no Buy Me a Coffee",
        "donate_later": "Talvez depois",
        "donate_hide": "Não mostrar novamente",
        # Diálogos
        "close_unsaved": "Há alterações não salvas no iPod.\nSalvar antes de sair?",
        "close_busy": "Há operações em andamento.\nAguarde a conclusão antes de fechar.",
    },
    "en": {
        "app_title": "iPod Manager",
        "drive_label": "Drive:",
        "drive_tip": "iPod drive (auto-detected or typed)",
        "no_ipod_short": "No iPod",
        "detect": "Detect iPod",
        "detect_tip": "Scan drives for iPod_Control (F5)",
        "add_files": "Add files",
        "add_files_tip": "Copy local audio files to the iPod",
        "remove": "Remove",
        "remove_tip": "Remove the selected tracks from the iPod (Del on table)",
        "bulk_edit": "Bulk edit",
        "bulk_edit_tip": "Apply artist/album/genre/year/rating to all selected tracks",
        "export": "Export",
        "export_tip": "Copy the selected tracks to a PC folder",
        "save": "Save to iPod",
        "save_tip": "Write changes to the iTunesDB, with automatic backup (Ctrl+S)",
        "eject": "Eject",
        "eject_tip": "Save changes and prepare the iPod for safe removal",
        "log": "Log",
        "options": "Options",
        "language": "Language",
        "support": "☕ Support the project",
        "about": "About iPod Manager",
        "playlists": "Playlists",
        "new_playlist": "+ New playlist",
        "new_playlist_tip": "Create a playlist on the iPod",
        "library": "Library (all tracks)",
        "about_text": "Music manager for classic iPods — edit tags, "
            "create playlists and download from YouTube Music, no iTunes needed.",
        "col_title": "Title",
        "col_artist": "Artist",
        "col_album": "Album",
        "col_genre": "Genre",
        "col_year": "Year",
        "col_num": "No.",
        "col_dur": "Length",
        "col_star": "★",
        "col_size": "Size",
        "col_added": "Added",
        "col_playlists": "Playlists",
        "filter_tip": "Filter tracks…",
        "drop_tip": "Drop audio files or tracks here",
        "add_to_playlist": "Add to playlist",
        "remove_from_playlist": "Remove from this playlist",
        "remove_from_ipod": "Remove from iPod",
        "export_tracks": "Export…",
        "bulk_edit_menu": "Bulk edit…",
        "rename_playlist": "Rename…",
        "delete_playlist": "Delete playlist",
        "new_playlist_menu": "New playlist…",
        "playlist_name_prompt": "Playlist name:",
        "yt_title": "YouTube Music",
        "search_tip": "Search YouTube Music…",
        "btn_search": "Search",
        "url_tip": "Paste a public YouTube Music playlist URL",
        "url_label": "Public playlist (URL or ID):",
        "btn_load_pl": "Load playlist",
        "dl_playlist_tip": "Downloads the loaded playlist and creates a playlist with the same name on the iPod",
        "retry_tip": "Re-downloads only the tracks that failed in the last batch",
        "cancel_dl_tip": "Stops the batch after the current track",
        "log_verbose_tip": "Logs more detail (useful for diagnosing failures)",
        "results": "Results",
        "playlist_label": "Playlist: —",
        "dl_selected": "Download selected",
        "dl_all": "Download all",
        "dl_playlist_ipod": "Download playlist to iPod",
        "chk_to_ipod": "Send directly to iPod",
        "limit_label": "Max per download:",
        "queue": "Download queue",
        "retry_failed": "Retry failed",
        "cancel_dl": "Cancel downloads",
        "log_dock": "Log",
        "log_open_file": "Open log file",
        "log_verbose": "Verbose (DEBUG)",
        "log_clear": "Clear",
        "ready": "Ready",
        "no_ipod": "No iPod loaded — click 'Detect iPod'",
        "selected_count": "selected",
        "saving": "Saving to iPod…",
        "saved": "Changes saved to the iPod",
        "lang_restart": "The language will be applied the next time the app starts.",
        "donate_title": "☕ Enjoying iPod Manager?",
        "donate_text": "This app is free and made with care.\n"
            "If it helped you, consider supporting development "
            "with a coffee — it keeps the project alive!",
        "donate_btn": "☕ Support on Buy Me a Coffee",
        "donate_later": "Maybe later",
        "donate_hide": "Don't show again",
        "close_unsaved": "There are unsaved changes on the iPod.\nSave before quitting?",
        "close_busy": "Operations are in progress.\nWait for them to finish before closing.",
    },
}

_lang = DEFAULT_LANG


def set_lang(code: str) -> None:
    """Define o idioma ativo (``pt`` ou ``en``); inválido → ``pt``."""
    global _lang
    _lang = code if code in S else DEFAULT_LANG


def lang() -> str:
    return _lang


def tr(key: str) -> str:
    """Traduz ``key`` no idioma ativo; fallback pt-BR → própria chave."""
    return S.get(_lang, {}).get(key) or S[DEFAULT_LANG].get(key, key)
