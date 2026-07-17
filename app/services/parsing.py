"""
Turns raw bytes (or a URL) into plain text for chunking. Each format uses a
real parser — nothing here approximates or fakes extraction.
"""
import csv
import io

import httpx
from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from pypdf import PdfReader


def parse_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def parse_csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = [", ".join(row) for row in reader]
    return "\n".join(rows)


def parse_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="ignore")


def parse_by_mime_or_extension(data: bytes, filename: str, mime_type: str | None) -> str:
    lower_name = filename.lower()
    if mime_type == "application/pdf" or lower_name.endswith(".pdf"):
        return parse_pdf(data)
    if lower_name.endswith(".docx") or mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return parse_docx(data)
    if lower_name.endswith(".csv") or mime_type == "text/csv":
        return parse_csv(data)
    return parse_txt(data)


def fetch_url_text(url: str, timeout: float = 20.0) -> str:
    """Fetches a page and extracts visible text, stripping scripts/styles/nav
    chrome. Real HTTP fetch + real HTML parsing — no placeholder content."""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "AIFlowBot/1.0 (+https://aiflow.io/bot)"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


def fetch_sitemap_urls(sitemap_url: str, timeout: float = 20.0, limit: int = 200) -> list[str]:
    """Parses a sitemap.xml and returns page URLs to crawl (capped at `limit`
    to keep a single ingestion job bounded)."""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(sitemap_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")
        urls = [loc.text.strip() for loc in soup.find_all("loc")]
        return urls[:limit]
