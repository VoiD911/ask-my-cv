from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

from ask_my_cv.container import build_embedder
from ask_my_cv.embeddings import EmbeddingProvider
from ask_my_cv.settings import load_settings
from ask_my_cv.vectorstore import Chunk, InMemoryVectorStore


def _split(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 2 > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        parts.append(current)
    return parts


def chunk_markdown(markdown: str, max_chars: int = 800) -> list[Chunk]:
    """Un passage par section `## …` ; une section trop longue est coupée entre paragraphes."""
    chunks: list[Chunk] = []
    section = "Intro"
    buffer: list[str] = []

    def flush() -> None:
        for part in _split("\n".join(buffer).strip(), max_chars):
            chunks.append(Chunk(id=f"c{len(chunks) + 1}", section=section, text=part))

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            buffer.clear()
            section = line[3:].strip()
        elif not line.startswith("# "):
            buffer.append(line)
    flush()
    return chunks


async def embed_chunks(chunks: list[Chunk], embedder: EmbeddingProvider) -> list[list[float]]:
    return await embedder.embed([f"{c.section}\n{c.text}" for c in chunks])


async def build_index(markdown: str, embedder: EmbeddingProvider) -> InMemoryVectorStore:
    chunks = chunk_markdown(markdown)
    vectors = await embed_chunks(chunks, embedder)
    return InMemoryVectorStore(chunks, vectors)


def main(argv: list[str] | None = None) -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Construit l'index vectoriel du CV.")
    parser.add_argument("--cv", type=Path, default=settings.cv_path)
    parser.add_argument("--out", type=Path, default=settings.index_path)
    parser.add_argument("--target", choices=["file", "dynamodb"], default="file")
    args = parser.parse_args(argv)
    markdown = args.cv.read_text(encoding="utf-8")
    if args.target == "dynamodb":
        from ask_my_cv.aws.dynamo import DynamoVectorStore
        from ask_my_cv.container import aws_client

        chunks = chunk_markdown(markdown)
        vectors = asyncio.run(embed_chunks(chunks, build_embedder(settings)))
        DynamoVectorStore(settings.chunks_table, aws_client("dynamodb", settings)).write(
            chunks, vectors
        )
        print(f"{len(chunks)} passages écrits -> dynamodb:{settings.chunks_table}")
        return
    store = asyncio.run(build_index(markdown, build_embedder(settings)))
    store.save(args.out)
    print(f"{len(store)} passages indexés -> {args.out}")


if __name__ == "__main__":
    main()
