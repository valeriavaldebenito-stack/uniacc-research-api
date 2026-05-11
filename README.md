# UNIACC Research API

Backend en FastAPI para usar con ChatGPT Actions.

## Render

Build Command:
pip install -r requirements.txt

Start Command:
uvicorn main:app --host 0.0.0.0 --port $PORT

## Endpoint

POST /research-website

Body:
{
  "website_url": "https://www.uniacc.cl",
  "questions": ["¿Qué programas online tiene UNIACC?"],
  "max_pages_to_review": 12,
  "download_brochures": true
}
