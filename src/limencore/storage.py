import json
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from limencore.ambient import AreaEnergia, ContextoAmbiente
from limencore.assunto import Assunto, limpar_rotulo, normalizar_assunto
from limencore.corte import Corte, FioPlanejado, Trecho, recortar
from limencore.despejo import Despejo
from limencore.fio import EstadoFio, Fio, Transicao, TransicaoInvalida
from limencore.janela import Evento, JanelaDoFio
from limencore.nota import Nota, TipoNota
from limencore.reservado import Reservado
from limencore.turno import Turno

_COLUNAS_FIO = "id, despejo_id, estado, criado_em, assunto_chave, juntado_em, ultimo_toque"

# destino que vira operacao desfazivel
_OPERACAO_DO_DESTINO = {EstadoFio.GUARDADO: "GUARDAR", EstadoFio.RESOLVIDO: "POUSAR"}

MOTIVO_DESFAZER = "desfazer"


def _trechos_para_json(trechos: tuple[Trecho, ...]) -> list[list[int]]:
    return [[t.inicio, t.fim] for t in trechos]


def _trechos_de_json(dados: list[list[int]]) -> tuple[Trecho, ...]:
    return tuple(Trecho(inicio, fim) for inicio, fim in dados)


def _aparar(texto: str, trechos: list[Trecho]) -> tuple[Trecho, ...]:
    # tira espacos das pontas da parte; trecho da ponta so de espacos sai inteiro
    partes = list(trechos)
    while partes and not recortar(texto, partes[0]).strip():
        partes.pop(0)
    while partes and not recortar(texto, partes[-1]).strip():
        partes.pop()
    if not partes:
        return ()
    pedaco = recortar(texto, partes[0])
    partes[0] = Trecho(partes[0].inicio + len(pedaco) - len(pedaco.lstrip()), partes[0].fim)
    pedaco = recortar(texto, partes[-1])
    partes[-1] = Trecho(partes[-1].inicio, partes[-1].fim - (len(pedaco) - len(pedaco.rstrip())))
    return tuple(partes)


@dataclass(frozen=True)
class Dia:
    despejos: list[Despejo]
    contexto: ContextoAmbiente | None


class Armazenamento:
    def __init__(self, caminho: str = "limencore.db", relogio: Callable[[], datetime] | None = None):
        self.caminho = caminho
        # relogio injetavel (testes); padrao = agora em UTC
        self._relogio = relogio if relogio is not None else (lambda: datetime.now(timezone.utc))
        self._conexao = sqlite3.connect(caminho)
        self._conexao.execute("PRAGMA foreign_keys = ON")
        self._conexao.execute("PRAGMA secure_delete = ON")
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
                assunto_chave TEXT REFERENCES assuntos(chave_norm),
                juntado_em TEXT REFERENCES fios(id),
                ultimo_toque TEXT
            )
            """
        )
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS trechos_fio (
                fio_id TEXT NOT NULL REFERENCES fios(id),
                ordem INTEGER NOT NULL,
                inicio INTEGER NOT NULL,
                fim INTEGER NOT NULL,
                PRIMARY KEY (fio_id, ordem)
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
                instante TEXT NOT NULL,
                motivo TEXT
            )
            """
        )
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS notas (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                fio_id TEXT NOT NULL REFERENCES fios(id),
                tipo TEXT NOT NULL,
                texto TEXT NOT NULL,
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
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS reservados (
                id TEXT PRIMARY KEY,
                texto TEXT NOT NULL,
                instante TEXT NOT NULL
            )
            """
        )
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS turnos (
                fio_id TEXT NOT NULL REFERENCES fios(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                texto TEXT NOT NULL,
                instante TEXT NOT NULL,
                PRIMARY KEY (fio_id, seq)
            )
            """
        )
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS operacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio_id TEXT NOT NULL REFERENCES fios(id),
                tipo TEXT NOT NULL,
                dados TEXT NOT NULL,
                instante TEXT NOT NULL,
                desfeita INTEGER NOT NULL DEFAULT 0
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
        if "juntado_em" not in colunas_fios:
            self._conexao.execute("ALTER TABLE fios ADD COLUMN juntado_em TEXT REFERENCES fios(id)")
        if "ultimo_toque" not in colunas_fios:
            self._conexao.execute("ALTER TABLE fios ADD COLUMN ultimo_toque TEXT")
        colunas_transicoes = {
            linha[1] for linha in self._conexao.execute("PRAGMA table_info(transicoes)")
        }
        if "motivo" not in colunas_transicoes:
            self._conexao.execute("ALTER TABLE transicoes ADD COLUMN motivo TEXT")
        self._conexao.commit()

    def agora(self) -> datetime:
        instante = self._relogio()
        if instante.tzinfo is None:
            raise ValueError("relogio sem timezone: use datetime timezone-aware (UTC)")
        return instante

    def _inserir_despejo(self, despejo: Despejo) -> None:
        # nao faz commit: quem chama decide
        self._conexao.execute(
            "INSERT INTO despejos (id, conteudo, instante) VALUES (?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (despejo.id, despejo.conteudo, despejo.instante.astimezone(timezone.utc).isoformat()),
        )

    def salvar(self, entry: Despejo):
        self._inserir_despejo(entry)
        self._conexao.commit()

    def _registrar_transicao(
        self, fio_id: str, de: EstadoFio | None, para: EstadoFio, motivo: str | None = None
    ) -> None:
        # sempre UTC no banco: ordenacao e filtros comparam texto
        self._conexao.execute(
            "INSERT INTO transicoes (fio_id, de, para, instante, motivo) VALUES (?, ?, ?, ?, ?)",
            (fio_id, de.name if de else None, para.name,
             self.agora().astimezone(timezone.utc).isoformat(), motivo),
        )

    def _inserir_fio(self, fio: Fio) -> None:
        # nao faz commit: quem chama decide
        self._conexao.execute(
            "INSERT INTO fios (id, despejo_id, estado, criado_em, assunto_chave, juntado_em, ultimo_toque)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (
                fio.id,
                fio.despejo_id,
                fio.estado.name,
                fio.criado_em.astimezone(timezone.utc).isoformat(),
                fio.assunto_chave,
                fio.juntado_em,
                fio.ultimo_toque.astimezone(timezone.utc).isoformat() if fio.ultimo_toque else None,
            ),
        )
        self._gravar_trechos(fio.id, fio.trechos)
        self._registrar_transicao(fio.id, None, fio.estado)

    def _gravar_trechos(self, fio_id: str, trechos: tuple[Trecho, ...]) -> None:
        # nao faz commit: quem chama decide
        self._conexao.execute("DELETE FROM trechos_fio WHERE fio_id = ?", (fio_id,))
        self._conexao.executemany(
            "INSERT INTO trechos_fio (fio_id, ordem, inicio, fim) VALUES (?, ?, ?, ?)",
            [(fio_id, ordem, t.inicio, t.fim) for ordem, t in enumerate(trechos)],
        )

    def salvar_fio(self, fio: Fio) -> None:
        try:
            self._inserir_fio(fio)
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def salvar_despejo_com_fios(self, despejo: Despejo, fios: list[Fio]) -> None:
        if not fios:
            raise ValueError("despejo precisa de ao menos um fio")
        if any(fio.despejo_id != despejo.id for fio in fios):
            raise ValueError("fio de outro despejo")
        try:
            self._inserir_despejo(despejo)
            for fio in fios:
                self._inserir_fio(fio)
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def _linha_para_fio(self, linha) -> Fio:
        id_, despejo_id, estado, criado_em, assunto_chave, juntado_em, ultimo_toque = linha
        return Fio(
            id=id_,
            despejo_id=despejo_id,
            estado=EstadoFio[estado],
            criado_em=datetime.fromisoformat(criado_em),
            assunto_chave=assunto_chave,
            trechos=self._trechos_do_fio(id_),
            juntado_em=juntado_em,
            ultimo_toque=datetime.fromisoformat(ultimo_toque) if ultimo_toque else None,
        )

    def _buscar_fio(self, fio_id: str) -> Fio:
        linha = self._conexao.execute(
            f"SELECT {_COLUNAS_FIO} FROM fios WHERE id = ?", (fio_id,)
        ).fetchone()
        if linha is None:
            raise ValueError("fio nao encontrado")
        return self._linha_para_fio(linha)

    def _filtro_estados(self, estados: Iterable[EstadoFio] | None, coluna: str = "estado") -> tuple[str, tuple]:
        # sem estados pedidos: tudo menos JUNTADO
        if estados is None:
            return f"{coluna} != ?", (EstadoFio.JUNTADO.name,)
        estados = tuple(estados)
        if not estados or any(not isinstance(e, EstadoFio) for e in estados):
            raise ValueError(f"estados invalidos: esperado EstadoFio, veio {estados!r}")
        return f"{coluna} IN ({', '.join('?' for _ in estados)})", tuple(e.name for e in estados)

    def _trechos_do_fio(self, fio_id: str) -> tuple[Trecho, ...]:
        cursor = self._conexao.execute(
            "SELECT inicio, fim FROM trechos_fio WHERE fio_id = ? ORDER BY ordem",
            (fio_id,),
        )
        return tuple(Trecho(inicio, fim) for inicio, fim in cursor.fetchall())

    def buscar_fios(self, despejo_id: str, estados: Iterable[EstadoFio] | None = None) -> list[Fio]:
        filtro, parametros = self._filtro_estados(estados)
        cursor = self._conexao.execute(
            f"""
            SELECT {_COLUNAS_FIO} FROM fios
              WHERE despejo_id = ? AND {filtro}
              ORDER BY criado_em, id
            """,
            (despejo_id, *parametros),
        )
        return [self._linha_para_fio(linha) for linha in cursor.fetchall()]

    def mesa(self) -> list[Fio]:
        cursor = self._conexao.execute(
            f"""
            SELECT {_COLUNAS_FIO} FROM fios
              WHERE estado IN ('ESCOLHIDO', 'JOGADO')
              ORDER BY ultimo_toque IS NULL, ultimo_toque DESC, criado_em, id
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
            SELECT f.id, f.despejo_id, f.estado, f.criado_em, f.assunto_chave,
                   f.juntado_em, f.ultimo_toque
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

    def fios_do_assunto(
        self, texto: str, desde: datetime | None = None, estados: Iterable[EstadoFio] | None = None
    ) -> list[Fio]:
        chave = normalizar_assunto(texto)
        filtro, parametros = self._filtro_estados(estados)
        valor = None
        if desde is not None:
            if desde.tzinfo is None:
                raise ValueError("desde sem timezone: use datetime timezone-aware")
            valor = desde.astimezone(timezone.utc).isoformat()
        cursor = self._conexao.execute(
            f"""
            SELECT {_COLUNAS_FIO} FROM fios
              WHERE assunto_chave = ?
                AND (? IS NULL OR criado_em >= ?)
                AND {filtro}
              ORDER BY criado_em, id
            """,
            (chave, valor, valor, *parametros),
        )
        return [self._linha_para_fio(linha) for linha in cursor.fetchall()]

    def _mudar_estado(self, fio: Fio, novo: EstadoFio) -> Fio:
        # nao faz commit: quem chama decide
        novo_fio = fio.transicionar(novo)
        cursor = self._conexao.execute(
            "UPDATE fios SET estado = ? WHERE id = ? AND estado = ?",
            (novo.name, fio.id, fio.estado.name),
        )
        if cursor.rowcount == 0:
            raise ValueError("fio nao encontrado ou estado desatualizado")
        self._registrar_transicao(fio.id, fio.estado, novo)
        return novo_fio

    def _registrar_operacao(self, fio_id: str, tipo: str, dados: dict) -> None:
        # nao faz commit: quem chama decide
        self._conexao.execute(
            "INSERT INTO operacoes (fio_id, tipo, dados, instante) VALUES (?, ?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (fio_id, tipo, json.dumps(dados), self.agora().astimezone(timezone.utc).isoformat()),
        )

    def _mudar_estado_com_operacao(self, fio: Fio, novo: EstadoFio) -> Fio:
        # nao faz commit: quem chama decide
        novo_fio = self._mudar_estado(fio, novo)
        tipo = _OPERACAO_DO_DESTINO.get(novo)
        if tipo is not None:
            self._registrar_operacao(
                fio.id, tipo, {"estado_anterior": fio.estado.name, "estado_posterior": novo.name}
            )
        return novo_fio

    def atualizar_estado(self, fio: Fio, novo: EstadoFio) -> Fio:
        if novo is EstadoFio.JUNTADO:
            raise TransicaoInvalida("JUNTADO so por juntar")
        try:
            novo_fio = self._mudar_estado_com_operacao(fio, novo)
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return novo_fio

    def guardar(self, fio: Fio) -> Fio:
        return self.atualizar_estado(fio, EstadoFio.GUARDADO)

    def _inserir_nota(self, fio_id: str, tipo: TipoNota, texto: str) -> Nota:
        # nao faz commit: quem chama decide
        nota = Nota(fio_id=fio_id, tipo=tipo, texto=texto, instante=self.agora())
        self._conexao.execute(
            "INSERT INTO notas (fio_id, tipo, texto, instante) VALUES (?, ?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (nota.fio_id, nota.tipo.name, nota.texto, nota.instante.astimezone(timezone.utc).isoformat()),
        )
        return nota

    def escrever(self, fio: Fio, texto: str) -> Nota:
        linha = self._conexao.execute(
            "SELECT estado FROM fios WHERE id = ?", (fio.id,)
        ).fetchone()
        if linha is None:
            raise ValueError("fio nao encontrado")
        if linha[0] != EstadoFio.ESCOLHIDO.name:
            raise ValueError("fio fora do quarto")
        try:
            nota = self._inserir_nota(fio.id, TipoNota.NOTA, texto)
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return nota

    def notas(self, fio_id: str) -> list[Nota]:
        cursor = self._conexao.execute(
            "SELECT fio_id, tipo, texto, instante FROM notas WHERE fio_id = ? ORDER BY seq",
            (fio_id,),
        )
        return [
            Nota(
                fio_id=fio_id_,
                tipo=TipoNota[tipo],
                texto=texto,
                instante=datetime.fromisoformat(instante),
            )
            for fio_id_, tipo, texto, instante in cursor.fetchall()
        ]

    def pousar(self, fio: Fio, frase: str | None = None) -> Fio:
        try:
            novo = self._mudar_estado_com_operacao(fio, EstadoFio.RESOLVIDO)
            if frase is not None and frase.strip():
                self._inserir_nota(fio.id, TipoNota.POUSO, frase)
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return novo

    def registrar_assunto(self, texto: str) -> Assunto:
        # nao faz commit: quem chama decide
        chave = normalizar_assunto(texto)
        rotulo = limpar_rotulo(texto)
        self._conexao.execute(
            "INSERT OR IGNORE INTO assuntos (chave_norm, rotulo, criado_em) VALUES (?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (chave, rotulo, self.agora().astimezone(timezone.utc).isoformat()),
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
            "SELECT fio_id, de, para, instante, motivo FROM transicoes WHERE fio_id = ? ORDER BY seq",
            (fio_id,),
        )
        return [
            Transicao(
                fio_id=fio_id_,
                de=EstadoFio[de] if de is not None else None,
                para=EstadoFio[para],
                instante=datetime.fromisoformat(instante),
                motivo=motivo,
            )
            for fio_id_, de, para, instante, motivo in cursor.fetchall()
        ]

    def registrar_turno(self, fio: Fio, texto: str) -> Turno:
        try:
            if self._conexao.execute("SELECT 1 FROM fios WHERE id = ?", (fio.id,)).fetchone() is None:
                raise ValueError("fio nao encontrado")
            (seq,) = self._conexao.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM turnos WHERE fio_id = ?", (fio.id,)
            ).fetchone()
            turno = Turno(fio_id=fio.id, seq=seq, texto=texto, instante=self.agora())
            self._conexao.execute(
                "INSERT INTO turnos (fio_id, seq, texto, instante) VALUES (?, ?, ?, ?)",
                # sempre UTC no banco: ordenacao e filtros comparam texto
                (turno.fio_id, turno.seq, turno.texto, turno.instante.astimezone(timezone.utc).isoformat()),
            )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return turno

    def turnos(self, fio_id: str) -> list[Turno]:
        cursor = self._conexao.execute(
            "SELECT fio_id, seq, texto, instante FROM turnos WHERE fio_id = ? ORDER BY seq",
            (fio_id,),
        )
        return [
            Turno(fio_id=fio_id_, seq=seq, texto=texto, instante=datetime.fromisoformat(instante))
            for fio_id_, seq, texto, instante in cursor.fetchall()
        ]

    def _ids_juntados(self, fio_id: str) -> list[str]:
        # o proprio fio e, recursivamente, os JUNTADO nele
        ids = [fio_id]
        for atual in ids:
            for (filho,) in self._conexao.execute(
                "SELECT id FROM fios WHERE juntado_em = ? AND estado = ? ORDER BY criado_em, id",
                (atual, EstadoFio.JUNTADO.name),
            ):
                if filho not in ids:
                    ids.append(filho)
        return ids

    def janela(self, fio_id: str) -> JanelaDoFio:
        linha = self._conexao.execute(
            "SELECT d.conteudo FROM fios f JOIN despejos d ON d.id = f.despejo_id WHERE f.id = ?",
            (fio_id,),
        ).fetchone()
        if linha is None:
            raise ValueError("fio nao encontrado")
        eventos = []
        for id_ in self._ids_juntados(fio_id):
            eventos += [(n.instante, 0, Evento("usuario", n.texto, n.instante)) for n in self.notas(id_)]
            eventos += [(t.instante, 1, Evento("agente", t.texto, t.instante)) for t in self.turnos(id_)]
        # empate no instante: nota antes de turno
        eventos.sort(key=lambda e: (e[0], e[1]))
        return JanelaDoFio(
            conteudo_do_despejo=linha[0],
            trechos=self._trechos_do_fio(fio_id),
            eventos=tuple(e for _, _, e in eventos),
        )

    def entrar(self, fio: Fio) -> Fio:
        atual = self._buscar_fio(fio.id)
        if atual.estado not in (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO):
            raise TransicaoInvalida(f"entrar exige JOGADO ou ESCOLHIDO, veio {atual.estado.name}")
        try:
            if atual.estado is EstadoFio.JOGADO:
                atual = self._mudar_estado(atual, EstadoFio.ESCOLHIDO)
            toque = self.agora()
            self._conexao.execute(
                "UPDATE fios SET ultimo_toque = ? WHERE id = ?",
                # sempre UTC no banco: ordenacao e filtros comparam texto
                (toque.astimezone(timezone.utc).isoformat(), atual.id),
            )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return replace(atual, ultimo_toque=toque)

    def juntar(self, a: Fio, b: Fio) -> Fio:
        if a.id == b.id:
            raise ValueError("juntar exige dois fios diferentes")
        fio_a, fio_b = self._buscar_fio(a.id), self._buscar_fio(b.id)
        if fio_a.despejo_id != fio_b.despejo_id:
            raise ValueError("juntar exige fios do mesmo despejo")
        for f in (fio_a, fio_b):
            if f.estado not in (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO):
                raise TransicaoInvalida(f"juntar exige JOGADO ou ESCOLHIDO, veio {f.estado.name}")
        # sobrevive o que vem primeiro no texto; () conta como 0
        sobrevivente, juntado = sorted(
            (fio_a, fio_b),
            key=lambda f: (f.trechos[0].inicio if f.trechos else 0, f.criado_em, f.id),
        )
        if not sobrevivente.trechos or not juntado.trechos:
            trechos = ()  # um deles ja e o despejo inteiro
        else:
            trechos = tuple(sorted(sobrevivente.trechos + juntado.trechos, key=lambda t: (t.inicio, t.fim)))
        escolhido = EstadoFio.ESCOLHIDO in (fio_a.estado, fio_b.estado)
        estado = EstadoFio.ESCOLHIDO if escolhido else EstadoFio.JOGADO
        try:
            novo = sobrevivente
            if novo.estado is not estado:
                novo = self._mudar_estado(novo, estado)
            self._gravar_trechos(novo.id, trechos)
            self._mudar_estado(juntado, EstadoFio.JUNTADO)
            self._conexao.execute(
                "UPDATE fios SET juntado_em = ? WHERE id = ?", (sobrevivente.id, juntado.id)
            )
            self._registrar_operacao(sobrevivente.id, "JUNTAR", {
                "outro": juntado.id,
                "estado_anterior": sobrevivente.estado.name,
                "estado_posterior": estado.name,
                "trechos_anteriores": _trechos_para_json(sobrevivente.trechos),
                "trechos_posteriores": _trechos_para_json(trechos),
                "outro_estado_anterior": juntado.estado.name,
            })
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return replace(novo, trechos=trechos)

    def dividir(self, fio: Fio, corte: int) -> tuple[Fio, Fio]:
        if not isinstance(corte, int) or isinstance(corte, bool):
            raise ValueError(f"corte invalido: esperado int, veio {corte!r}")
        atual = self._buscar_fio(fio.id)
        if atual.estado is not EstadoFio.ESCOLHIDO:
            raise TransicaoInvalida(f"dividir exige ESCOLHIDO, veio {atual.estado.name}")
        texto = self.buscar_despejo(atual.despejo_id).conteudo
        trechos = sorted(atual.trechos or (Trecho(0, len(texto)),), key=lambda t: t.inicio)
        dentro = any(t.inicio < corte < t.fim for t in trechos)
        na_fronteira = any(antes.fim <= corte <= depois.inicio for antes, depois in zip(trechos, trechos[1:]))
        if not (dentro or na_fronteira):
            raise ValueError(f"corte fora dos trechos do fio: {corte}")
        primeira, segunda = [], []
        for t in trechos:
            if t.fim <= corte:
                primeira.append(t)
            elif t.inicio >= corte:
                segunda.append(t)
            else:
                primeira.append(Trecho(t.inicio, corte))
                segunda.append(Trecho(corte, t.fim))
        partes = Corte(fios=(FioPlanejado(_aparar(texto, primeira)), FioPlanejado(_aparar(texto, segunda))))
        partes.validar_para(texto)
        trechos_primeira, trechos_segunda = (g.trechos for g in partes.fios)
        novo = Fio(despejo_id=atual.despejo_id, criado_em=self.agora(), trechos=trechos_segunda)
        try:
            self._gravar_trechos(atual.id, trechos_primeira)
            self._inserir_fio(novo)
            self._registrar_operacao(atual.id, "DIVIDIR", {
                "outro": novo.id,
                "trechos_anteriores": _trechos_para_json(atual.trechos),
                "trechos_posteriores": _trechos_para_json(trechos_primeira),
            })
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return replace(atual, trechos=trechos_primeira), novo

    def _voltar_estado(self, fio_id: str, de: EstadoFio, para: EstadoFio) -> None:
        # so o desfazer usa: ignora TRANSICOES
        # nao faz commit: quem chama decide
        cursor = self._conexao.execute(
            "UPDATE fios SET estado = ? WHERE id = ? AND estado = ?",
            (para.name, fio_id, de.name),
        )
        if cursor.rowcount == 0:
            raise ValueError("fio nao encontrado ou estado desatualizado")
        self._registrar_transicao(fio_id, de, para, motivo=MOTIVO_DESFAZER)

    def desfazer(self, fio: Fio, janela_segundos: float = 10) -> Fio:
        linha = self._conexao.execute(
            """
            SELECT id, fio_id, tipo, dados, instante FROM operacoes
              WHERE desfeita = 0 AND (fio_id = ? OR json_extract(dados, '$.outro') = ?)
              ORDER BY id DESC LIMIT 1
            """,
            (fio.id, fio.id),
        ).fetchone()
        if linha is None:
            raise ValueError("nada para desfazer neste fio")
        operacao_id, dono, tipo, dados, instante = linha
        dados = json.loads(dados)
        if self.agora() - datetime.fromisoformat(instante) >= timedelta(seconds=janela_segundos):
            raise ValueError("fora da janela de desfazer")
        envolvidos = [dono] + ([dados["outro"]] if "outro" in dados else [])
        marcas = ", ".join("?" for _ in envolvidos)
        depois = self._conexao.execute(
            f"""
            SELECT 1 FROM operacoes
              WHERE desfeita = 0 AND id > ?
                AND (fio_id IN ({marcas}) OR json_extract(dados, '$.outro') IN ({marcas}))
            """,
            (operacao_id, *envolvidos, *envolvidos),
        ).fetchone()
        if depois is not None:
            raise ValueError("operacao nao e a ultima dos fios envolvidos")
        try:
            principal = self._buscar_fio(dono)
            if tipo in ("GUARDAR", "POUSAR"):
                if principal.estado.name != dados["estado_posterior"]:
                    raise ValueError("estado desatualizado: o fio mudou depois da operacao")
                self._voltar_estado(dono, principal.estado, EstadoFio[dados["estado_anterior"]])
            elif tipo == "JUNTAR":
                outro = self._buscar_fio(dados["outro"])
                if (
                    principal.estado.name != dados["estado_posterior"]
                    or principal.trechos != _trechos_de_json(dados["trechos_posteriores"])
                    or outro.estado is not EstadoFio.JUNTADO
                    or outro.juntado_em != dono
                ):
                    raise ValueError("estado desatualizado: os fios mudaram depois da operacao")
                self._gravar_trechos(dono, _trechos_de_json(dados["trechos_anteriores"]))
                if dados["estado_anterior"] != dados["estado_posterior"]:
                    self._voltar_estado(dono, principal.estado, EstadoFio[dados["estado_anterior"]])
                self._conexao.execute("UPDATE fios SET juntado_em = NULL WHERE id = ?", (outro.id,))
                self._voltar_estado(outro.id, EstadoFio.JUNTADO, EstadoFio[dados["outro_estado_anterior"]])
            elif tipo == "DIVIDIR":
                outro = self._buscar_fio(dados["outro"])
                if (
                    principal.trechos != _trechos_de_json(dados["trechos_posteriores"])
                    or outro.estado not in (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO)
                ):
                    raise ValueError("estado desatualizado: os fios mudaram depois da operacao")
                self._gravar_trechos(dono, _trechos_de_json(dados["trechos_anteriores"]))
                self._voltar_estado(outro.id, outro.estado, EstadoFio.JUNTADO)
                self._conexao.execute("UPDATE fios SET juntado_em = ? WHERE id = ?", (dono, outro.id))
            else:
                raise ValueError(f"tipo de operacao desconhecido: {tipo!r}")
            self._conexao.execute("UPDATE operacoes SET desfeita = 1 WHERE id = ?", (operacao_id,))
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return self._buscar_fio(fio.id)

    def guardar_reservado(self, texto: str, instante: datetime) -> Reservado:
        reservado = Reservado(id=str(uuid.uuid4()), texto=texto, instante=instante)
        self._conexao.execute(
            "INSERT INTO reservados (id, texto, instante) VALUES (?, ?, ?)",
            # sempre UTC no banco: ordenacao e filtros comparam texto
            (reservado.id, reservado.texto, reservado.instante.astimezone(timezone.utc).isoformat()),
        )
        self._conexao.commit()
        return reservado

    def listar_reservados(self) -> list[Reservado]:
        cursor = self._conexao.execute(
            "SELECT id, texto, instante FROM reservados ORDER BY instante, id"
        )
        return [
            Reservado(id=id_, texto=texto, instante=datetime.fromisoformat(instante))
            for id_, texto, instante in cursor.fetchall()
        ]

    def apagar_reservado(self, id_: str) -> None:
        cursor = self._conexao.execute("DELETE FROM reservados WHERE id = ?", (id_,))
        if cursor.rowcount == 0:
            raise ValueError("reservado nao encontrado")
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
                self.agora().astimezone(timezone.utc).isoformat(),
            ),
        )
        self._conexao.commit()

    def buscar_despejo(self, id_: str) -> Despejo | None:
        linha = self._conexao.execute(
            "SELECT id, conteudo, instante FROM despejos WHERE id = ?", (id_,)
        ).fetchone()
        if linha is None:
            return None
        id_, conteudo, instante = linha
        return Despejo(id=id_, conteudo=conteudo, instante=datetime.fromisoformat(instante))

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
