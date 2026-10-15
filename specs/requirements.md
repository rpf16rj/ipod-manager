# Requirements — iPod Manager

## Visão geral

Aplicativo desktop simples para Windows que permite gerenciar as músicas de um
iPod clássico/nano conectado via USB **sem iTunes**: listar, editar metadados,
enviar e remover músicas, criar playlists no iPod e criar playlists a partir de
playlists públicas do YouTube Music (baixando as faixas e copiando para o iPod).

Idioma da UI: português (pt-BR).

## Dispositivo alvo (detectado no ambiente)

- iPod Nano 1ª geração, 2 GB, modelo MA004, montado em `I:\`
- Assinatura do banco: HASH58 (via FirewireGuid)
- Backend: biblioteca `pygpod` (Python puro, já validada contra o dispositivo real:
  111 faixas / 7 playlists lidas com sucesso)

## Requisitos funcionais

### R1 — Detecção e leitura do iPod
- R1.1 Detectar automaticamente unidades removíveis que contenham `iPod_Control`.
- R1.2 Permitir selecionar/re-selecionar a unidade manualmente (ex.: `I:\`).
- R1.3 Ler a biblioteca (iTunesDB): título, artista, álbum, gênero, duração,
  ano, nº da faixa, avaliação, play count.
- R1.4 Exibir informações do dispositivo: modelo, capacidade, espaço usado/livre,
  total de faixas.

### R2 — Gerenciamento de músicas
- R2.1 Listar todas as músicas em tabela com busca/filtro e ordenação por coluna.
- R2.2 Editar metadados inline (título, artista, álbum, gênero, ano, nº faixa,
  avaliação) e persistir no iTunesDB ao salvar.
- R2.3 Enviar arquivos de áudio locais (MP3, M4A/AAC, WAV, FLAC→conversão se
  necessário) para o iPod — via botão "Adicionar arquivos" e drag-and-drop.
- R2.4 Remover músicas do iPod (remover do iTunesDB **e** apagar o arquivo em
  `iPod_Control\Music`), com confirmação.
- R2.5 Exportar (copiar) música do iPod para pasta local.
- R2.6 Todas as gravações devem passar por "Aplicar/Salvar" explícito, com
  backup automático do diretório `iPod_Control\iTunes` antes de cada escrita.

### R3 — Playlists no iPod
- R3.1 Listar playlists existentes (exceto master/podcast) com contagem de faixas.
- R3.2 Criar, renomear e excluir playlists.
- R3.3 Adicionar/remover faixas em uma playlist (seleção múltipla na biblioteca).
- R3.4 Exibir conteúdo da playlist selecionada.

### R4 — YouTube Music → iPod
- R4.1 Buscar músicas no YouTube Music por texto (via `ytmusicapi`), mostrando
  título, artista, álbum e duração nos resultados.
- R4.2 Colar URL de **playlist pública** do YouTube Music
  (`music.youtube.com/playlist?list=...`) e listar todas as faixas.
- R4.3 Baixar faixas selecionadas/todas via `yt-dlp` (videoId → watch URL),
  converter para MP3 192kbps via ffmpeg (binário de `imageio-ffmpeg`),
  gravar tags ID3 (título, artista, álbum, capa) via `mutagen`.
- R4.4 Ao baixar uma playlist, criar playlist homônima no iPod e adicionar as
  faixas baixadas a ela.
- R4.5 Fila de download com progresso por item e possibilidade de enviar
  "direto para o iPod" ou apenas para pasta local de staging.

### R5 — Robustez e UX
- R5.1 Operações longas (leitura do DB, downloads, sync) em threads — UI nunca
  trava; barra de status com progresso.
- R5.2 Erros claros em português (iPod não encontrado, disco cheio, falha de
  download por faixa — continuar com as demais).
- R5.3 Botão "Ejetar" que salva o DB e orienta a remoção segura.
- R5.4 Antes de qualquer `save()` no iPod: backup de `iPod_Control\iTunes\*`
  para `iPod_Control\iTunes.backup-<timestamp>` no próprio iPod.

## Requisitos não funcionais

- N1 Python 3.14, Windows 10/11, sem dependência de iTunes nem de .NET.
- N2 GUI em PySide6, janela única, layout em 3 zonas: playlists (esquerda),
  tabela de músicas (centro), busca/fila YouTube Music (direita ou aba).
- N3 Persistência de configuração mínima (pasta de staging, última unidade) em
  `%APPDATA%\iPodManager\config.json`.
- N4 Sem telemetria, sem rede além de YouTube Music.

## Fora de escopo (v1)

- Vídeos, fotos, podcasts, capas personalizadas avançadas, smart playlists.
- Autenticação no YouTube Music (apenas conteúdo público).
- iPods com firmware Rockbox; iPhones/iPod Touch (usam outro banco).
