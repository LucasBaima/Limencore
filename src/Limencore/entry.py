from dataclasses import dataclass
from datetime import datetime, timezone
import uuid



@dataclass
class ThoughtEntry:  #ThoughtEntry = "entrada-pensamento"
instante: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
id: str = field(default_factory=lambda: str(uuid.uuid4()))


 def __post_init__(self):
        if not self.conteudo or not self.conteudo.strip():
            raise ValueError("conteudo vazio: uma entrada-pensamento exige um despejo")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")

    