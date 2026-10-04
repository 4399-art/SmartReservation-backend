from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


def load_markdown(file_path: str | Path) -> str:
    return Path(file_path).read_text(encoding="utf-8")


def split_markdown(text: str) -> list[Document]:
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "H1"),
            ("##", "H2"),
            ("###", "H3"),
            ("####", "H4"),
        ],
        return_each_line=False,
    )
    splits = header_splitter.split_text(text)

    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n#### ", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )
    return recursive_splitter.split_documents(splits)


def load_and_split_markdown(file_path: str | Path) -> list[Document]:
    text = load_markdown(file_path)
    return split_markdown(text)