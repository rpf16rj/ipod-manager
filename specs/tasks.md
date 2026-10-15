# Tasks — iPod Manager

- [x] T1 (Agente 1) `ipod_manager/ipod_service.py` conforme contrato do design.md
      + `tests/test_ipod_service.py` (leitura real em `I:\`, sem escrita) — 8 testes ok
- [x] T2 (Agente 2) `ipod_manager/downloader.py` conforme contrato
      + `tests/test_downloader.py` — 3 testes ok incl. download real c/ tags+capa
- [x] T3 (Agente 3) `ipod_manager/gui/app.py` + `gui/workers.py` + `main.py`
      conforme layout do design.md — integração real validada
- [x] T4 Integração: imports cruzados, `requirements.txt`, `README.md` (como rodar)
      — fix: import QApplication ausente em app.py
- [x] T5 Smoke test leitura: `ipod_service` lista 111 faixas / 7 playlists em `I:\`
- [x] T6 Teste de escrita real: backup manual de `I:\iPod_Control\iTunes`,
      `add_files` com 1 mp3 de teste + `save()`, reler e conferir; depois remover
      — add/edit/remove persistem; fix: colisão de nome de backup em saves <1s
- [x] T7 Teste downloader: buscar termo, baixar 1 faixa p/ staging, validar tags
- [x] T8 Validar GUI abre (`python main.py`), fluxo leitura → edição → salvar
