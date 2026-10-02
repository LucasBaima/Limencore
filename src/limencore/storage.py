import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from limencore.ambient import AreaEnergia, ContextoAmbiente
from limencore.assunto import Assunto, limpar_rotulo, normalizar_assunto
from limencore.despejo import Despejo
from limencore.fio import EstadoFio, Fio, Transicao


@dataclass(frozen=True)
class Dia:
    despejos: list[Despejo]
    contexto: ContextoAmbiente | None


class Armazenamento:
    def __init__(self, caminho: str = "limencore.db"):
        self.caminho = caminho
        self._conexao = sqlite3.connect(caminho)
        self._conexao.execute("PRAGMA foreign_keys = ON")
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
            CREATE TABLE IF NOT EXISTS assuntos (
                chave_norm TEXT PRIMARY KEY,
                rotulo TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS fios (
                id TEXT PRIMARY KEY,
                despejo_id TEXT NOT NULL REFERENCES despejos(id),
                estado TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                assunto_chave TEXT REFERENCES assuntos(chave_norm)
            )
            """
        )
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS transicoes (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                fio_id TEXT NOT NULL REFERENCES fios(id),
                de TEXT,
                para TEXT NOT NULL,
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
        colunas_fios = {
            linha[1] for linha in self._conexao.execute("PRAGMA table_info(fios)")
        }
        if "assunto_chave" not in colunas_fios:
            self._conexao.execute(
                "ALTER TABLE fios ADD COLUMN assunto_chave TEXT REFERENCES assuntos(chave_norm)"
            )
        self._conexao.commit()

    def salvar(self, entry: Despejo):
        self._conexao.execute(
            "INSERT INTO despejos (id, conteudo, instante) VALUES (?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (entry.id, entry.conteudo, entry.instante.astimezone(timezone.utc).isoformat()),
        )
        self._conexao.commit()

    def _registrar_transicao(self, fio_id: str, de: EstadoFio | None, para: EstadoFio) -> None:
        # sempre UTC no banco: ordenacao e filtros comparam texto
        self._conexao.execute(
            "INSERT INTO transicoes (fio_id, de, para, instante) VALUES (?, ?, ?, ?)",
            (fio_id, de.name if de else None, para.name,
             datetime.now(timezone.utc).isoformat()),
        )

    def salvar_fio(self, fio: Fio) -> None:
        try:
            self._conexao.execute(
                "INSERT INTO fios (id, despejo_id, estado, criado_em, assunto_chave)"
                " VALUES (?, ?, ?, ?, ?)",
                # sempre UTC no banco: ordenacao e filtros comparam texto
                (
                    fio.id,
                    fio.despejo_id,
                    fio.estado.name,
                    fio.criado_em.astimezone(timezone.utc).isoformat(),
                    fio.assunto_chave,
                ),
            )
            self._registrar_transicao(fio.id, None, fio.estado)
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def _linha_para_fio(self, linha) -> Fio:
        id_, despejo_id, estado, criado_em, assunto_chave = linha
        return Fio(
            id=id_,
            despejo_id=despejo_id,
            estado=EstadoFio[estado],
            criado_em=datetime.fromisoformat(criado_em),
            assunto_chave=assunto_chave,
        )

    def buscar_fios(self, despejo_id: str) -> list[Fio]:
        cursor = self._conexao.execute(
            """
            SELECT id, despejo_id, estado, criado_em, assunto_chave FROM fios
              WHERE despejo_id = ?
              ORDER BY criado_em, id
            """,
            (despejo_id,),
        )
        return [self._linha_para_fio(linha) for linha in cursor.fetchall()]

    def mesa(self) -> list[Fio]:
        cursor = self._conexao.execute(
            """
            SELECT id, despejo_id, estado, criado_em, assunto_chave FROM fios
              WHERE estado IN ('ESCOLHIDO', 'JOGADO')
              ORDER BY CASE estado WHEN 'ESCOLHIDO' THEN 0 ELSE 1 END, criado_em, id
            """
        )
        return [self._linha_para_fio(linha) for linha in cursor.fetchall()]

    def guardados(self, desde: datetime | None = None) -> list[Fio]:
        # "mais recente" = ultima transicao para GUARDADO pelo maior seq, nunca pelo horario.
        # Fios sem transicao (dados anteriores ao historico) vao pro fim.
        filtro = ""
        parametros: tuple = ()
        if desde is not None:
            if desde.tzinfo is None:
                raise ValueError("desde sem timezone: use datetime timezone-aware")
            filtro = "AND t.instante >= ?"
            parametros = (desde.astimezone(timezone.utc).isoformat(),)
        cursor = self._conexao.execute(
            f"""
            SELECT f.id, f.despejo_id, f.estado, f.criado_em, f.assunto_chave
              FROM fios f
              LEFT JOIN (
                  SELECT fio_id, MAX(seq) AS seq FROM transicoes
                   WHERE para = 'GUARDADO' GROUP BY fio_id
              ) g ON g.fio_id = f.id
              LEFT JOIN transicoes t ON t.seq = g.seq
              WHERE f.estado = 'GUARDADO'
              {filtro}
              ORDER BY g.seq IS NULL, g.seq DESC, f.criado_em, f.id
            """,
            parametros,
        )
        return [self._linha_para_fio(linha) for linha in cursor.fetchall()]

    def atualizar_estado(self, fio: Fio, novo: EstadoFio) -> Fio:
        novo_fio = fio.transicionar(novo)
        try:
            cursor = self._conexao.execute(
                "UPDATE fios SET estado = ? WHERE id = ? AND estado = ?",
                (novo.name, fio.id, fio.estado.name),
            )
            if cursor.rowcount == 0:
                raise ValueError("fio nao encontrado ou estado desatualizado")
            self._registrar_transicao(fio.id, fio.estado, novo)
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return novo_fio

    def registrar_assunto(self, texto: str) -> Assunto:
        # nao faz commit: quem chama decide
        chave = normalizar_assunto(texto)
        rotulo = limpar_rotulo(texto)
        self._conexao.execute(
            "INSERT OR IGNORE INTO assuntos (chave_norm, rotulo, criado_em) VALUES (?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (chave, rotulo, datetime.now(timezone.utc).isoformat()),
        )
        (rotulo_gravado,) = self._conexao.execute(
            "SELECT rotulo FROM assuntos WHERE chave_norm = ?", (chave,)
        ).fetchone()
        return Assunto(chave, rotulo_gravado)

    def buscar_assunto(self, chave: str) -> Assunto | None:
        linha = self._conexao.execute(
            "SELECT chave_norm, rotulo FROM assuntos WHERE chave_norm = ?", (chave,)
        ).fetchone()
        if linha is None:
            return None
        return Assunto(*linha)

    def marcar_assunto(self, fio: Fio, texto: str) -> Fio:
        try:
            assunto = self.registrar_assunto(texto)
            cursor = self._conexao.execute(
                "UPDATE fios SET assunto_chave = ? WHERE id = ?",
                (assunto.chave, fio.id),
            )
            if cursor.rowcount == 0:
                raise ValueError("fio nao encontrado")
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return replace(fio, assunto_chave=assunto.chave)

    def historico(self, fio_id: str) -> list[Transicao]:
        cursor = self._conexao.execute(
            "SELECT fio_id, de, para, instante FROM transicoes WHERE fio_id = ? ORDER BY seq",
            (fio_id,),
        )
        return [
            Transicao(
                fio_id=fio_id_,
                de=EstadoFio[de] if de is not None else None,
                para=EstadoFio[para],
                instante=datetime.fromisoformat(instante),
            )
            for fio_id_, de, para, instante in cursor.fetchall()
        ]

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
