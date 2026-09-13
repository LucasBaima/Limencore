import json
import sqlite3
from datetime import datetime, timezone

from limencore.ambient import AreaEnergia, ContextoAmbiente
from limencore.entry import ThoughtEntry


class Armazenamento:
    def __init__(self, caminho: str = "limencore.db"):
        self.caminho = caminho
        self._conexao = sqlite3.connect(caminho)
        self._inicializar()

    def _inicializar(self):
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS thoughts (
                id TEXT PRIMARY KEY,
                conteudo TEXT NOT NULL,
                instante TEXT NOT NULL
            )
            """
        )
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS contexto_dia (
                entry_date TEXT PRIMARY KEY,
                sono_horas REAL,
                sono_interrupcoes INTEGER,
                cafeina_mg REAL,
                energia TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conexao.commit()

    def salvar(self, entry: ThoughtEntry):
        self._conexao.execute(
            "INSERT INTO thoughts (id, conteudo, instante) VALUES (?, ?, ?)",
            (entry.id, entry.conteudo, entry.instante.isoformat()),
        )
        self._conexao.commit()

    def salvar_contexto(self, entry_date: str, contexto: ContextoAmbiente):
        energia_json = json.dumps({a.name: v for a, v in contexto.energia.items()})
        self._conexao.execute(
            """
            INSERT INTO contexto_dia
              (entry_date, sono_horas, sono_interrupcoes, cafeina_mg, energia, created_at)
              VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(entry_date) DO UPDATE SET
              sono_horas = excluded.sono_horas,
              sono_interrupcoes = excluded.sono_interrupcoes,
              cafeina_mg = excluded.cafeina_mg,
              energia = excluded.energia
            """,
            (
                entry_date,
                contexto.sono_horas,
                contexto.sono_interrupcoes,
                contexto.cafeina_mg,
                energia_json,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conexao.commit()

    def listar(self) -> list[ThoughtEntry]:
        cursor = self._conexao.execute(
            "SELECT id, conteudo, instante FROM thoughts ORDER BY instante"
        )
        return [
            ThoughtEntry(
                id=id_,
                conteudo=conteudo,
                instante=datetime.fromisoformat(instante),
            )
            for id_, conteudo, instante in cursor.fetchall()
        ]

    def buscar_contexto(self, entry_date: str) -> ContextoAmbiente | None:
        cursor = self._conexao.execute(
            """
            SELECT sono_horas, sono_interrupcoes, cafeina_mg, energia
              FROM contexto_dia WHERE entry_date = ?
            """,
            (entry_date,),
        )
        linha = cursor.fetchone()
        if linha is None:
            return None
        sono_horas, sono_interrupcoes, cafeina_mg, energia = linha
        energia_dict = {
            AreaEnergia[nome]: v for nome, v in json.loads(energia or "{}").items()
        }
        return ContextoAmbiente(
            sono_horas=sono_horas,
            sono_interrupcoes=sono_interrupcoes,
            cafeina_mg=cafeina_mg,
            energia=energia_dict,
        )

    def fechar(self):
        self._conexao.close()
