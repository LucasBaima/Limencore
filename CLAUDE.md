# CLAUDE.md — Limencore (repositório público)

Guia para agentes de código neste repositório. Este arquivo é público:
só comandos e convenções de trabalho.

## O que é
Núcleo aberto (Apache 2.0) de uma biblioteca de journaling de pensamentos,
em Python 3.12. Código em `src/limencore/`, testes em `tests/`.

## Ambiente
O `.venv/` é local de cada máquina e não vai pro Git. Se ele não existir,
crie e instale as dependências:

Windows:
    python -m venv .venv
    .venv\Scripts\python -m pip install -e ".[dev]"

Linux (Debian; pode exigir `sudo apt install python3-venv`):
    python3 -m venv .venv
    .venv/bin/python -m pip install -e ".[dev]"

## Testes
Windows:  ./.venv/Scripts/python -m pytest
Linux:    .venv/bin/python -m pytest

Use sempre o Python do `.venv`. Não crie venv descartável se o `.venv` existir.

## Regras de trabalho
- `git pull` antes de começar.
- Não commitar nem dar push: isso é do mantenedor.
- `pytest` inteiro verde antes de encerrar qualquer tarefa.
- Nunca deixar nada em stage: sem `git add`, sem `git mv` (use `mv`).
- Commits seguem Conventional Commits (feat, fix, refactor, test, docs, chore).
- Executar exatamente o escopo da ordem recebida; não refatorar o que não foi pedido.

## Limite deste repositório
Aqui só entra mecânica: guardar, buscar, validar, transicionar.
Não adicionar lógica que interprete o conteúdo escrito pelo usuário.
