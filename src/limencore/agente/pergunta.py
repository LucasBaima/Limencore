from dataclasses import dataclass
from enum import Enum


class CamadaContencao(Enum):
    SITUACAO = "Situação"
    PENSAMENTO = "Pensamento"
    EMOCAO = "Emoção"
    PREOCUPACAO = "Preocupação"


@dataclass(frozen=True)
class Pergunta:
    texto: str
    camada: CamadaContencao | None = None 
