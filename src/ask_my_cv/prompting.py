from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ask_my_cv.vectorstore import Hit


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system: str

    def render(self, question: str, hits: list[Hit], canary: str) -> tuple[str, str]:
        system = self.system.replace("{canary}", canary)
        sources = "\n\n".join(
            f"[{i}] ({hit.chunk.section}) {hit.chunk.text}" for i, hit in enumerate(hits, 1)
        )
        user = f"Sources :\n{sources or '(aucune)'}\n\nQuestion : {question}"
        return system, user


def load_template(path: Path) -> PromptTemplate:
    """Le nom de fichier porte la version : `answer@v1.md` -> name=answer, version=v1."""
    name, _, version = path.stem.partition("@")
    if not version:
        raise ValueError(f"nom de template sans version : {path.name}")
    return PromptTemplate(name=name, version=version, system=path.read_text(encoding="utf-8").strip())
