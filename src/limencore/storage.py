import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from limencore.ambient import AreaEnergia, ContextoAmbiente
from limencore.despejo import Despejo


@dataclass(frozen=True)
class Dia:
    despejos: list[Despejo]
    contexto: ContextoAmbiente | None


class Armazenamento:
    def __init__(self, caminho: str = "limencore.db"):
        self.caminho = caminho
        self._conexao = sqlite3.connect(caminho)
        self._inicializar()

    def _inicializar(self):
        tabelas = {
            nome for (nome,) in self._conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "thoughts" in tabelas and "despejos" not in tabelas:
            self._conexao.execute("ALTER TABLE thoughts RENAME TO despejos")

        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS despejos (
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
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS categorias (
                chave_norm TEXT PRIMARY KEY,
                rotulo     TEXT NOT NULL
            )
            """
        )
        self._conexao.commit()

    def salvar(self, entry: Despejo):
        self._conexao.execute(
            "INSERT INTO despejos (id, conteudo, instante) VALUES (?, ?, ?)",
            (entry.id, entry.conteudo, entry.instante.isoformat()),
        )
        self._conexao.commit()

    def _canonicalizar_energia(self, energia: dict[str, int]) -> dict[str, int]:
        defaults = {area.value for area in AreaEnergia}
        resultado = {}
        for chave, valor in energia.items():
            if chave in defaults:
                canonica = chave
            else:
                norm = chave.strip().casefold()
                self._conexao.execute(
                    "INSERT OR IGNORE INTO categorias (chave_norm, rotulo) VALUES (?, ?)",
                    (norm, chave.strip()),
                )
                canonica = self._conexao.execute(
                    "SELECT rotulo FROM categorias WHERE chave_norm = ?", (norm,)
                ).fetchone()[0]
            resultado[canonica] = valor
        return resultado

    def salvar_contexto(self, entry_date: str, contexto: ContextoAmbiente):
        energia = self._canonicalizar_energia(contexto.energia)
        energia_json = json.dumps(energia)
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

    def listar(self) -> list[Despejo]:
        cursor = self._conexao.execute(
            "SELECT id, conteudo, instante FROM despejos ORDER BY instante"
        )
        return [
            Despejo(
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
        energia_dict = json.loads(energia or "{}")
        return ContextoAmbiente(
            sono_horas=sono_horas,
            sono_interrupcoes=sono_interrupcoes,
            cafeina_mg=cafeina_mg,
            energia=energia_dict,
        )

    def buscar_por_data(self, data_local: date, tz: ZoneInfo) -> list[Despejo]:
        #def buscar_por_data(self, data_local: date, tz: ZoneInfo) -> list[Despejo]:
        # Lembrar -> despejos guardam 'instante' em UTC; "o dia X local" é uma JANELA em UTC,
        # não um match de data. Montei meia-noite local -> +1 dia, convertemos as
        # duas pontas pra UTC e filtramos [inicio, fim). Assim um despejo das 23h
        # não vaza pro dia seguinte.

        #O 'tz' tem que ser o mesmo usado ao salvar o
        # entry_date, senão despejo e contexto discordam sobre que dia é.


        inicio_local = datetime(
            data_local.year, data_local.month, data_local.day, tzinfo=tz
        )
        fim_local = inicio_local + timedelta(days=1)
        inicio_utc = inicio_local.astimezone(timezone.utc)
        fim_utc = fim_local.astimezone(timezone.utc)
        cursor = self._conexao.execute(
            """
            SELECT id, conteudo, instante FROM despejos
              WHERE instante >= ? AND instante < ?
              ORDER BY instante
            """,
            (inicio_utc.isoformat(), fim_utc.isoformat()),
        )
        return [
            Despejo(
                id=id_,
                conteudo=conteudo,
                instante=datetime.fromisoformat(instante),
            )
            for id_, conteudo, instante in cursor.fetchall()
        ]

    def buscar_dia(self, data_local: date, tz: ZoneInfo) -> Dia:
        despejos = self.buscar_por_data(data_local, tz)
        contexto = self.buscar_contexto(data_local.isoformat())
        return Dia(despejos=despejos, contexto=contexto)

    def listar_contextos(
        self, inicio: str, fim: str
    ) -> list[tuple[str, ContextoAmbiente]]:
        cursor = self._conexao.execute(
            """
            SELECT entry_date, sono_horas, sono_interrupcoes, cafeina_mg, energia
              FROM contexto_dia
              WHERE entry_date >= ? AND entry_date <= ?
              ORDER BY entry_date
            """,
            (inicio, fim),
        )
        resultado = []
        for entry_date, sono_horas, sono_interrupcoes, cafeina_mg, energia in cursor.fetchall():
            energia_dict = json.loads(energia or "{}")
            resultado.append(
                (
                    entry_date,
                    ContextoAmbiente(
                        sono_horas=sono_horas,
                        sono_interrupcoes=sono_interrupcoes,
                        cafeina_mg=cafeina_mg,
                        energia=energia_dict,
                    ),
                )
            )
        return resultado

    def fechar(self):
        self._conexao.close()
