from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import re
import io
from pypdf import PdfReader

app = FastAPI(title="UNIACC Website Research API", version="1.0.0")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UNIACCResearchBot/1.0; +https://www.uniacc.cl)"
}

class ResearchRequest(BaseModel):
    website_url: HttpUrl = "https://www.uniacc.cl"
    questions: List[str]
    max_pages_to_review: int = 12
    download_brochures: bool = True
    include_program_pages: bool = True
    extract_prices: bool = True
    language: str = "es"

class Answer(BaseModel):
    question: str
    answer: str
    sources: List[str]

class Brochure(BaseModel):
    title: str
    pdf_url: str
    related_program: Optional[str] = None
    summary: Optional[str] = None

class Program(BaseModel):
    program_name: str
    category: Optional[str] = None
    modality: Optional[str] = None
    duration: Optional[str] = None
    price: Optional[str] = None
    program_url: str

class ResearchResponse(BaseModel):
    executive_summary: str
    answers: List[Answer]
    programs_detected: List[Program]
    brochures_found: List[Brochure]
    visited_pages: List[str]

def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:6000]

def same_domain(url: str, root: str) -> bool:
    return urlparse(url).netloc.replace("www.", "") == urlparse(root).netloc.replace("www.", "")

def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        if "text/html" not in r.headers.get("content-type", ""):
            return ""
        return r.text
    except Exception:
        return ""

def extract_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    keywords = [
        "magister", "magíster", "postgrado", "diplomado", "admision", "admisión",
        "carrera", "programa", "online", "advance", "educacion-continua", "pdf", "brochure"
    ]
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if href.startswith("http") and same_domain(href, base_url):
            low = href.lower()
            anchor = a.get_text(" ", strip=True).lower()
            if any(k in low or k in anchor for k in keywords):
                links.append(href.split("#")[0])
    return list(dict.fromkeys(links))

def page_text_and_title(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    heading = h1.get_text(" ", strip=True) if h1 else title
    text = clean_text(soup.get_text(" ", strip=True))
    return {"title": title, "heading": heading, "text": text}

def find_pdfs(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    pdfs = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if ".pdf" in href.lower():
            pdfs.append(href.split("#")[0])
    return list(dict.fromkeys(pdfs))

def read_pdf_summary(pdf_url: str) -> str:
    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        reader = PdfReader(io.BytesIO(r.content))
        text = ""
        for page in reader.pages[:3]:
            text += page.extract_text() or ""
        return clean_text(text)[:1200]
    except Exception:
        return ""

def detect_program(page: Dict[str, str], url: str) -> Optional[Program]:
    text = page["text"].lower()
    title = page["heading"] or page["title"]
    program_keywords = ["magíster", "magister", "diplomado", "doctorado", "postítulo", "carrera", "programa"]
    if not any(k in text or k in title.lower() for k in program_keywords):
        return None

    category = None
    for k in ["Magíster", "Diplomado", "Doctorado", "Postítulo", "Carrera", "Programa"]:
        if k.lower().replace("í","i") in title.lower().replace("í","i") or k.lower() in text:
            category = k
            break

    modality = None
    if "online" in text or "100% online" in text:
        modality = "Online"
    elif "presencial" in text:
        modality = "Presencial"
    elif "semipresencial" in text or "híbrida" in text or "hibrida" in text:
        modality = "Semipresencial/Híbrida"

    duration = None
    dur_match = re.search(r"(\d+\s*(meses|semestres|años|horas))", page["text"], re.IGNORECASE)
    if dur_match:
        duration = dur_match.group(1)

    price = None
    price_match = re.search(r"(\$[\d\.\,]+|UF\s*[\d\.\,]+|arancel[^\.]{0,80})", page["text"], re.IGNORECASE)
    if price_match:
        price = price_match.group(1)

    return Program(
        program_name=title[:180],
        category=category,
        modality=modality,
        duration=duration,
        price=price,
        program_url=url
    )

def simple_answer(question: str, pages: List[Dict[str, Any]], brochures: List[Brochure]) -> Answer:
    q_terms = [t.lower() for t in re.findall(r"\w+", question) if len(t) > 3]
    scored = []
    for p in pages:
        hay = (p["title"] + " " + p["heading"] + " " + p["text"]).lower()
        score = sum(1 for t in q_terms if t in hay)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored[:3]]

    if not top:
        return Answer(
            question=question,
            answer="No encontré información suficiente en las páginas revisadas para responder con seguridad.",
            sources=[]
        )

    snippets = []
    sources = []
    for p in top:
        sources.append(p["url"])
        snippets.append(f"{p['heading']}: {p['text'][:700]}")

    if brochures:
        snippets.append("Brochures/PDFs detectados: " + "; ".join([b.title for b in brochures[:5]]))

    return Answer(
        question=question,
        answer="Información encontrada: " + " ".join(snippets)[:2500],
        sources=list(dict.fromkeys(sources))
    )

@app.get("/")
def health():
    return {"status": "ok", "message": "UNIACC Research API funcionando"}

@app.post("/research-website", response_model=ResearchResponse)
def research_website(req: ResearchRequest):
    root = str(req.website_url).rstrip("/")
    html = fetch_html(root)
    if not html:
        raise HTTPException(status_code=400, detail="No fue posible leer la página principal.")

    candidate_links = [root] + extract_links(html, root)
    candidate_links = candidate_links[: max(1, req.max_pages_to_review)]

    visited_pages = []
    page_records = []
    programs = []
    pdf_urls = []

    for url in candidate_links:
        page_html = fetch_html(url)
        if not page_html:
            continue
        visited_pages.append(url)
        data = page_text_and_title(page_html)
        data["url"] = url
        page_records.append(data)

        if req.include_program_pages:
            program = detect_program(data, url)
            if program:
                programs.append(program)

        if req.download_brochures:
            pdf_urls.extend(find_pdfs(page_html, url))

    pdf_urls = list(dict.fromkeys(pdf_urls))[:8]
    brochures = []
    for pdf in pdf_urls:
        summary = read_pdf_summary(pdf)
        title = pdf.split("/")[-1].replace("-", " ").replace("_", " ")[:120]
        brochures.append(Brochure(title=title, pdf_url=pdf, summary=summary))

    answers = [simple_answer(q, page_records, brochures) for q in req.questions]

    return ResearchResponse(
        executive_summary=f"Se revisaron {len(visited_pages)} páginas internas de {root}, se detectaron {len(programs)} posibles programas y {len(brochures)} brochures/PDFs.",
        answers=answers,
        programs_detected=programs[:20],
        brochures_found=brochures,
        visited_pages=visited_pages
    )