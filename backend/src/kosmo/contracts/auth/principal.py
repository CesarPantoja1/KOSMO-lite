from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    scopes: frozenset[str] = field(default_factory=lambda: frozenset[str]())

    def has_scopes(self, required: frozenset[str]) -> bool:
        if "*" in self.scopes:
            return True
        return required.issubset(self.scopes)
