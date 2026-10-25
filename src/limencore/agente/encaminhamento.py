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


class Familia(Enum):  # de quem e o risco
    SI_MESMA = "SiMesma"                # a propria pessoa
    MACHUCAR_ALGUEM = "MachucarAlguem"  # a pessoa contra outra
    ALGUEM_EM_RISCO = "AlguemEmRisco"   # outra pessoa contra si


@runtime_checkable
class DetectorDeEncaminhamento(Protocol):
    """Costura do portao. O publico entrega um detector simples;
    o privado pluga o que entende contexto."""

    def avaliar(self, texto: str) -> Passagem: ...


@runtime_checkable
class DetectorComFamilia(DetectorDeEncaminhamento, Protocol):
    """Opcional. Quem so tem avaliar() fala da propria pessoa (SI_MESMA)."""

    def avaliar_com_familia(self, texto: str) -> tuple[Passagem, Familia]: ...


@runtime_checkable
class DetectorComFamilias(DetectorComFamilia, Protocol):
    """Opcional. Diz tambem as outras familias que dispararam no mesmo texto."""

    def avaliar_com_familias(self, texto: str) -> tuple[Passagem, Familia, tuple[Familia, ...]]: ...


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

# Familia MACHUCAR_ALGUEM. Intencao explicita de ferir outra pessoa, em primeira
# pessoa e com alvo dito: inicio + verbo + alvo. Sozinha confere; raiva e
# xingamento nao entram.
INICIOS_DE_INTENCAO: tuple[str, ...] = (
    "quero", "vou", "vontade de", "penso em", "to pensando em", "estou pensando em",
)
VERBOS_CONTRA_OUTROS: tuple[str, ...] = (
    "matar", "machucar", "esfaquear", "envenenar", "atirar em", "atirar no", "atirar na", "bater em",
)
# Alvo: um destes, ou um determinante seguido de uma palavra, ou um nome
# proprio (inicial maiuscula no texto original).
ALVOS_PRONOMES: tuple[str, ...] = ("ele", "ela", "alguem")
DETERMINANTES_DE_ALVO: tuple[str, ...] = (
    "o", "a", "meu", "minha", "meus", "minhas", "esse", "essa", "aquele", "aquela", "seu", "sua",
)
INTENCOES_CONTRA_OUTROS: tuple[str, ...] = (  # frases fechadas, alem do padrao
    "i want to kill him", "i want to kill her", "i'm going to kill him", "i'm going to kill her",
)
# Plano ou meio. So contam junto de uma intencao: ai encaminham.
MARCADORES_DE_PLANO: tuple[str, ...] = (
    "arma", "revolver", "pistola", "uma faca", "a faca", "com faca", "minha faca", "veneno",
    "ja planejei", "tenho um plano", "planejei tudo",
    "hoje a noite", "esta noite", "amanha", "horario",
    "gun", "knife", "tonight", "i have a plan",
)
# Familia ALGUEM_EM_RISCO. Relato de que outra pessoa quer se machucar ou morrer.
# Sempre encaminham.
RELATOS_DE_RISCO_ALHEIO: tuple[str, ...] = (
    "disse que quer morrer", "falou que quer morrer", "diz que quer morrer", "fala que quer morrer",
    "ele quer morrer", "ela quer morrer", "falou em morrer",
    "falou em se matar", "fala em se matar", "disse que vai se matar", "falou que vai se matar",
    "ele quer se matar", "ela quer se matar", "pensa em se matar", "pensando em se matar",
    "tentou se matar", "ameacou se matar",
    "disse que quer se machucar", "falou que quer se machucar", "esta se cortando",
    "falou em suicidio", "falou de suicidio", "tentou suicidio", "pensa em suicidio",
    "nao quer mais viver", "tirar a propria vida",
    "she wants to die", "he wants to die", "wants to kill himself", "wants to kill herself",
)


def _sem_acento(texto: str) -> str:  # guarda maiusculas: o nome proprio depende delas
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.split())


def _normalizar(texto: str) -> str:
    return _sem_acento(texto).casefold()


def _frases(texto: str) -> list[str]:
    return re.split(r"[.!?;\n]+", texto)


def _alternativas(itens: tuple[str, ...]) -> list[str]:
    return [re.escape(n) for n in (_normalizar(i) for i in itens) if n]


def _compilar(itens: tuple[str, ...], figurados: list[str]) -> re.Pattern | None:
    alt = _alternativas(itens)
    if not alt:
        return None
    excecao = r"(?!\s+(?:" + "|".join(figurados) + r")\b)" if figurados else ""
    return re.compile(r"\b(?:" + "|".join(alt) + r")\b" + excecao)


def _compilar_contra_outros(
    inicios: tuple[str, ...], verbos: tuple[str, ...], frases: tuple[str, ...], figurados: list[str]
) -> re.Pattern | None:
    # roda sobre _sem_acento (sem casefold): so o nome proprio olha a maiuscula
    ini, verb = _alternativas(inicios), _alternativas(verbos)
    partes = _alternativas(frases)
    if ini and verb:
        alvo = (
            r"(?:" + "|".join(_alternativas(ALVOS_PRONOMES))
            + r"|(?:" + "|".join(_alternativas(DETERMINANTES_DE_ALVO)) + r")\s+\w+"
            + r"|(?-i:[A-Z])\w*)"
        )
        partes.insert(0, r"(?:" + "|".join(ini) + r")\s+(?:" + "|".join(verb) + r")\s+" + alvo)
    if not partes:
        return None
    excecao = r"(?!\s+(?:" + "|".join(figurados) + r")\b)" if figurados else ""
    return re.compile(r"\b(?:" + "|".join(partes) + r")\b" + excecao, re.IGNORECASE)


class DetectorPorExpressoes:
    """Detector publico:  Nao entende contexto ainda."""

    def __init__(
        self,
        explicitas: tuple[str, ...] = EXPRESSOES_EXPLICITAS,
        ambiguos: tuple[str, ...] = TERMOS_AMBIGUOS,
        figurados: tuple[str, ...] = COMPLEMENTOS_FIGURADOS,
        inicios: tuple[str, ...] = INICIOS_DE_INTENCAO,
        verbos: tuple[str, ...] = VERBOS_CONTRA_OUTROS,
        contra_outros: tuple[str, ...] = INTENCOES_CONTRA_OUTROS,
        planos: tuple[str, ...] = MARCADORES_DE_PLANO,
        risco_alheio: tuple[str, ...] = RELATOS_DE_RISCO_ALHEIO,
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
        self._contra_outros = _compilar_contra_outros(inicios, verbos, contra_outros, fig)
        self._plano = _compilar(planos, [])
        self._risco_alheio = _compilar(risco_alheio, fig)

    def avaliar(self, texto: str) -> Passagem:
        return self.avaliar_com_familia(texto)[0]

    def avaliar_com_familia(self, texto: str) -> tuple[Passagem, Familia]:
        passagem, familia, _ = self.avaliar_com_familias(texto)
        return passagem, familia

    def avaliar_com_familias(self, texto: str) -> tuple[Passagem, Familia, tuple[Familia, ...]]:
        com_maiusculas = _sem_acento(texto)
        t = com_maiusculas.casefold()
        # o que e dito de outra pessoa nao conta como sinal da propria
        propria = com_maiusculas
        if self._contra_outros is not None:
            propria = self._contra_outros.sub(" | ", propria)
        propria = propria.casefold()
        if self._risco_alheio is not None:
            propria = self._risco_alheio.sub(" | ", propria)
        contra_outro = Passagem.SEGUIR
        if self._contra_outros is not None and self._contra_outros.search(com_maiusculas):
            contra_outro = Passagem.ENCAMINHAR if self._plano_junto(texto) else Passagem.CONFERIR
        risco_alheio = Passagem.SEGUIR
        if self._risco_alheio is not None and self._risco_alheio.search(t):
            risco_alheio = Passagem.ENCAMINHAR
        # ordem = prioridade da familia; a passagem e a mais grave que casou
        casaram = [
            (p, f) for p, f in (
                (self._avaliar_propria(propria), Familia.SI_MESMA),
                (contra_outro, Familia.MACHUCAR_ALGUEM),
                (risco_alheio, Familia.ALGUEM_EM_RISCO),
            ) if p is not Passagem.SEGUIR
        ]
        if not casaram:
            return Passagem.SEGUIR, Familia.SI_MESMA, ()
        grave = any(p is Passagem.ENCAMINHAR for p, _ in casaram)
        familias = tuple(f for _, f in casaram)
        return (Passagem.ENCAMINHAR if grave else Passagem.CONFERIR), familias[0], familias[1:]

    def _plano_junto(self, texto: str) -> bool:
        # o plano so conta na mesma frase da intencao
        if self._plano is None:
            return False
        for frase in map(_sem_acento, _frases(texto)):
            if self._contra_outros.search(frase) and self._plano.search(frase.casefold()):
                return True
        return False

    def _avaliar_propria(self, t: str) -> Passagem:
        if self._explicito.search(t):
            return Passagem.ENCAMINHAR
        if self._ambiguo is not None and self._ambiguo.search(t):
            return Passagem.CONFERIR
        return Passagem.SEGUIR


ORIGENS_DA_CONFERENCIA = ("escrever", "pousar")


@dataclass(frozen=True)
class Encaminhamento:  # a saida do sistema: nada foi salvo
    texto: str
    instante: datetime
    oferece_retorno: bool  # False = sem o "nao era isso"
    familia: Familia = Familia.SI_MESMA
    origem: str | None = None  # como na Conferencia; o quarto usa para voltar
    outras_familias: tuple[Familia, ...] = ()  # as que tambem dispararam

    def __post_init__(self):
        if self.origem is not None and self.origem not in ORIGENS_DA_CONFERENCIA:
            raise ValueError(f"origem invalida: esperado um de {ORIGENS_DA_CONFERENCIA}, veio {self.origem!r}")


@dataclass(frozen=True)
class Conferencia:  # a pergunta antes da porta: nada foi salvo
    texto: str
    instante: datetime
    origem: str | None = None  # no quarto: "escrever" ou "pousar"; None = entrada
    familia: Familia = Familia.SI_MESMA
    outras_familias: tuple[Familia, ...] = ()  # as que tambem dispararam

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
