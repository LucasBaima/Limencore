import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol, runtime_checkable


class Passagem(Enum):
    SEGUIR = "Seguir"          # segue o fluxo normal
    CONFERIR = "Conferir"      # pergunta o sentido antes de decidir
    ENCAMINHAR = "Encaminhar"  # sai do sistema: ajuda humana


@runtime_checkable
class DetectorDeEncaminhamento(Protocol):
    """Costura do portao. O publico entrega um detector simples;
    o privado pluga o que entende contexto."""

    def avaliar(self, texto: str) -> Passagem: ...


# PROVISORIAS: nao validadas. Nenhuma exposicao a usuario real antes da
# validacao por profissionais.
# Explicitas: intencao em primeira pessoa. Sempre encaminham.
EXPRESSOES_EXPLICITAS: tuple[str, ...] = (
    "quero me matar", "penso em me matar", "pensando em me matar",
    "vontade de me matar", "nao quero mais viver",
    "tirar minha vida", "tirar a minha vida",
    "acabar com minha vida", "acabar com a minha vida",
    "suicidio", "suicida", "suicidar",
    "quero me machucar", "vontade de me machucar",
    "quero me cortar", "vontade de me cortar",
    "kill myself", "end my life", "suicide", "want to hurt myself",
)
# Ambiguos: podem ser figura de linguagem, passado, outra pessoa. Conferem.
TERMOS_AMBIGUOS: tuple[str, ...] = (
    "me matar", "morrer", "morrendo", "morri", "quero sumir", "vou sumir",
    "sumir pra sempre", "quero desaparecer", "vou desaparecer",
    "nao aguento mais", "nunca mais acordar", "deixar voces em paz",
    "me machucar", "queria desaparecer",
    "estou cansado de existir",
    "não tenho mais saída",
    "cheguei ao fim da linha",
    "queria evaporar",
    "quero escapar de mim mesmo",
    "queria acordar em outra vida",
    "estou perdendo a vontade de tudo",
    "não vejo futuro para mim",
    "queria que tudo acabasse",
    "vou desaparecer da vida de vocês",
    "não aguento continuar assim",
    "queria descansar para sempre",
    "seria melhor se eu não existisse",
    "queria deixar de ser eu",
    "não queria sentir mais nada",
)

# Complementos que, logo depois de um termo ambiguo, deixam o uso figurado claro.
# Cuidado: cada complemento DESLIGA a conferencia. So entram completamentos de
# expressoes figuradas por natureza, nunca motivos ("com essa situacao").
COMPLEMENTOS_FIGURADOS: tuple[str, ...] = (
    "de rir", "de sono", "de fome", "de sede", "de vergonha", "de calor",
    "de frio", "de saudade", "de tedio", "de medo", "de estudar", "de trabalhar", "de tanto rir",
    "de vergonha alheia", "de sono acumulado", "de tanto estudar",
    "de tanto trabalhar",
    "por uns dias",
    "por algumas horas",
    "das redes sociais",
    "desse lugar",
    "dessa conversa",
    "dessa discussão",
    "da vida agitada",
    "no sentido figurado",
    "como forma de expressão",
    "em tom de brincadeira",
    "metaforicamente",
)


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.casefold().split())


def _alternativas(itens: tuple[str, ...]) -> list[str]:
    return [re.escape(n) for n in (_normalizar(i) for i in itens) if n]


class DetectorPorExpressoes:
    """Detector publico:  Nao entende contexto ainda."""

    def __init__(
        self,
        explicitas: tuple[str, ...] = EXPRESSOES_EXPLICITAS,
        ambiguos: tuple[str, ...] = TERMOS_AMBIGUOS,
        figurados: tuple[str, ...] = COMPLEMENTOS_FIGURADOS,
    ):
        exp = _alternativas(explicitas)
        if not exp:
            raise ValueError("lista de expressoes explicitas vazia")
        self._explicito = re.compile(r"\b(?:" + "|".join(exp) + r")\b")
        amb = _alternativas(ambiguos)
        fig = _alternativas(figurados)
        if amb:
            excecao = r"(?!\s+(?:" + "|".join(fig) + r")\b)" if fig else ""
            self._ambiguo = re.compile(r"\b(?:" + "|".join(amb) + r")\b" + excecao)
        else:
            self._ambiguo = None

    def avaliar(self, texto: str) -> Passagem:
        t = _normalizar(texto)
        if self._explicito.search(t):
            return Passagem.ENCAMINHAR
        if self._ambiguo is not None and self._ambiguo.search(t):
            return Passagem.CONFERIR
        return Passagem.SEGUIR


@dataclass(frozen=True)
class Encaminhamento:  # a saida do sistema: nada foi salvo
    texto: str
    instante: datetime
    oferece_retorno: bool  # False = sem o "nao era isso"


ORIGENS_DA_CONFERENCIA = ("escrever", "pousar")


@dataclass(frozen=True)
class Conferencia:  # a pergunta antes da porta: nada foi salvo
    texto: str
    instante: datetime
    origem: str | None = None  # no quarto: "escrever" ou "pousar"; None = entrada

    def __post_init__(self):
        if self.origem is not None and self.origem not in ORIGENS_DA_CONFERENCIA:
            raise ValueError(f"origem invalida: esperado um de {ORIGENS_DA_CONFERENCIA}, veio {self.origem!r}")


class RegistroDaSessao:
    """Lembra encaminhamentos recentes SO em memoria. Nunca vai pro banco."""

    # PROVISORIA: janela a validar com profissionais.
    JANELA_PADRAO = timedelta(minutes=30)

    def __init__(self, janela: timedelta = JANELA_PADRAO):
        self._janela = janela
        self._instantes: list[datetime] = []

    def registrar(self, instante: datetime) -> None:
        self._instantes.append(instante)

    def houve_recente(self, instante: datetime) -> bool:
        return any(timedelta(0) <= instante - i <= self._janela for i in self._instantes)
