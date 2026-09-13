from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class ThoughtEntry:  # ThoughtEntry = "entrada-pensamento"
    conteudo: str
    instante: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if not self.conteudo or not self.conteudo.strip():
            raise ValueError("conteudo vazio: uma entrada-pensamento exige um despejo")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")
        try:
            u = uuid.UUID(self.id)
        except (ValueError, TypeError):
            raise ValueError(f"id invalido (nao e uuid): {self.id!r}")
        if u.version != 4:
            raise ValueError(f"id nao e uuid4: {self.id!r}")
