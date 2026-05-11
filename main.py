from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

app = FastAPI(
    title="UNIACC Research API",
    version="1.0.0"
)

class ResearchRequest(BaseModel):
    website_url: str = Field(default="https://www.uniacc.cl")
    questions: List[str]
    download_brochures: Optional[bool] = True
    max_pages_to_review: Optional[int] = 5
    language: Optional[str] = "es"

class Answer(BaseModel):
    question: str
    answer: str
    sources: List[str]

class ResearchResponse(BaseModel):
    executive_summary: str
    answers: List[Answer]
    brochures_found: List[dict] = []
    visited_pages: List[str] = []

@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "UNIACC Research API is running"
    }

@app.post("/research-website", response_model=ResearchResponse)
def research_website(request: ResearchRequest):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
response = requests.get(
    request.website_url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"
    },
    timeout=15
)

if response.status_code == 403:
    clean_url = request.website_url.replace("https://", "").replace("http://", "")
    fallback_url = f"https://r.jina.ai/http://r.jina.ai/http://r.jina.ai/http://{clean_url}"

    response = requests.get(
        fallback_url,
        timeout=20
    )

if response.status_code >= 400:
    raise HTTPException(
        status_code=400,
        detail=f"No se pudo acceder al sitio. Código: {response.status_code}"
    )

        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.string.strip() if soup.title and soup.title.string else "Sin título"

        text = soup.get_text(separator=" ", strip=True)
        text = text[:6000]

        links = []
        brochures = []

        base_domain = urlparse(request.website_url).netloc

        for a in soup.find_all("a", href=True):
            href = urljoin(request.website_url, a["href"])
            label = a.get_text(strip=True)

            if urlparse(href).netloc == base_domain:
                links.append(href)

            if href.lower().endswith(".pdf") or "brochure" in href.lower():
                brochures.append({
                    "title": label or "Documento encontrado",
                    "pdf_url": href,
                    "summary": "Documento o brochure detectado en el sitio."
                })

        links = list(dict.fromkeys(links))[:request.max_pages_to_review]

        answers = []

        for question in request.questions:
            answer_text = (
                f"Se revisó la página {request.website_url}. "
                f"El sitio analizado corresponde a: {title}. "
                f"Contenido relevante detectado: {text[:1200]}..."
            )

            answers.append({
                "question": question,
                "answer": answer_text,
                "sources": [request.website_url]
            })

        return {
            "executive_summary": f"Investigación inicial completada sobre {request.website_url}. Se revisó la página principal y se detectaron enlaces internos y posibles documentos.",
            "answers": answers,
            "brochures_found": brochures,
            "visited_pages": [request.website_url] + links
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno: {str(e)}"
        )
