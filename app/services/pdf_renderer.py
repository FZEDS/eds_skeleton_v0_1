# app/services/pdf_renderer.py

from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
KEEP_HTML_DEBUG = os.getenv("EDS_KEEP_HTML_DEBUG", "0").lower() in {"1","true","yes"}


APP_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = APP_DIR / "templates"
OUT_DIR = APP_DIR.parent / "var" / "generated"

def render_pdf(template_rel_path: str, context: dict, out_name: str | None = None) -> str:
    # Import tardif de WeasyPrint pour éviter de bloquer le démarrage si libs manquantes
    from weasyprint import HTML

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    html_tpl = env.get_template(template_rel_path)
    html_str = html_tpl.render(**context)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not out_name:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"cdi_{ts}.pdf"
    out_path = OUT_DIR / out_name
    
    # Debug optionnel : garder l'HTML rendu à côté du PDF (déactivé par défaut)
    if KEEP_HTML_DEBUG:
        html_debug_path = out_path.with_suffix(".html")
        with open(html_debug_path, "w", encoding="utf-8") as f:
            f.write(html_str)


    HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf(str(out_path))
    return str(out_path)


# 👇 NOUVEAU : rendu PDF en mémoire (pour l’aperçu)
def render_pdf_bytes(template_rel_path: str, context: dict) -> bytes:
    from weasyprint import HTML
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    html_tpl = env.get_template(template_rel_path)
    html_str = html_tpl.render(**context)
    # write_pdf() sans target retourne directement des bytes
    return HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()
