import html
import json
import logging
import re
import unicodedata
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import ProceedingsPaper, ProceedingsSource
from .paper_search import _clean_title, normalize_title
from .utils_conference import _download_capped

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
DOWNLOAD_TIMEOUT = (10, 120)
ACCEPTED_TYPES = ("json", "html", "text/plain", "javascript")
SYNC_LOCK_TTL = 3600
MIN_TITLE_CHARS = 10
MIN_LINK_TITLE_WORDS = 4
MAX_LINK_TITLE_WORDS = 40
TITLE_MAX = 500
URL_MAX = 500

PARSER_GUIDE = [
    {
        "parser": "miccai_json",
        "sites": "MICCAI open access (2024 onward)",
        "url": "https://papers.miccai.org/miccai-{year}/js/search.json",
        "options": "none",
        "notes": "Search index behind papers.miccai.org; links straight to the open-access PDF "
                 "(the paper page with reviews only when no PDF is listed).",
    },
    {
        "parser": "virtual_site_json",
        "sites": "NeurIPS, ICML, ICLR and CVPR conference websites (shared virtual-site platform)",
        "url": "https://neurips.cc/static/virtual/data/neurips-{year}-orals-posters.json "
               "(same path on icml.cc, iclr.cc, cvpr.thecvf.com)",
        "options": "none",
        "notes": "Published around the conference and can be partial before it "
                 "(CVPR 2026 listed ~400 of ~4000 papers); prefer cvf_html for CVPR.",
    },
    {
        "parser": "cvf_html",
        "sites": "CVF open access (CVPR, ICCV, WACV) and ECVA (ECCV)",
        "url": "https://openaccess.thecvf.com/CVPR{year}?day=all, https://www.ecva.net/papers.php",
        "options": '{"href_contains": "eccv_2024"} — needed for ECVA, whose page lists every ECCV year',
        "notes": "Reads dt.ptitle titles, the authors line and the [pdf] link. Always use ?day=all on CVF.",
    },
    {
        "parser": "html_selectors",
        "sites": "Any other paper-list page with a regular structure",
        "url": "the list page",
        "options": '{"item": "li.paper", "title": "h3", "authors": ".authors", '
                   '"link": "a.paper-link", "pdf": "a.pdf"} — only "item" is required',
        "notes": "One record per item; title defaults to the item text and link to its first link.",
    },
    {
        "parser": "html_links",
        "sites": "Last resort for unknown pages",
        "url": "the list page",
        "options": '{"href_contains": "/paper/"} (optional)',
        "notes": "Every link whose text looks like a title. No authors, so only close title matches are accepted.",
    },
]


def _unicode_name(letter):
    return "LAMDA" if letter == "lambda" else letter.upper()


GREEK = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau "
         "upsilon phi chi psi omega").split()
LATEX_SYMBOLS = {
    **{name: unicodedata.lookup(f"GREEK SMALL LETTER {_unicode_name(name)}") for name in GREEK},
    **{name.capitalize(): unicodedata.lookup(f"GREEK CAPITAL LETTER {_unicode_name(name)}") for name in GREEK},
    "varepsilon": "ε", "vartheta": "ϑ", "varphi": "φ", "varrho": "ϱ", "varsigma": "ς", "varpi": "ϖ",
    "infty": "∞", "partial": "∂", "nabla": "∇", "times": "×", "cdot": "·", "pm": "±", "mp": "∓",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "approx": "≈", "sim": "~", "propto": "∝",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔", "Rightarrow": "⇒",
    "in": "∈", "subset": "⊂", "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "neg": "¬", "land": "∧", "lor": "∨", "oplus": "⊕", "otimes": "⊗", "circ": "∘", "star": "⋆",
    "ell": "ℓ", "hbar": "ℏ", "sum": "∑", "prod": "∏", "int": "∫", "sqrt": "√", "prime": "′",
    "ldots": "…", "dots": "…", "cdots": "⋯", "mid": "|", "vert": "|", "ast": "*", "dagger": "†",
    "o": "ø", "O": "Ø", "ss": "ß", "l": "ł", "L": "Ł", "aa": "å", "AA": "Å", "ae": "æ", "AE": "Æ",
    "i": "ı", "j": "ȷ", "S": "§",
}
LATEX_ACCENTS = {
    "'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303", "=": "\u0304",
    ".": "\u0307", "c": "\u0327", "v": "\u030c", "u": "\u0306", "H": "\u030b", "k": "\u0328", "r": "\u030a",
}
LATEX_ESCAPES = {"&": "&", "%": "%", "_": "_", "#": "#", "$": "$", "{": "{", "}": "}"}
SUPERSCRIPT = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
QUOTE_PAIRS = {'"': '"', "'": "'", "“": "”", "‘": "’", "«": "»", "„": "“"}
ABBREVIATIONS = {"al", "etc", "vs", "inc", "ltd", "co", "eg", "ie"}
LATEX_MARKERS = re.compile(r"\\|\$.*\$|[{}`]")


def _accent(accent, letter):
    if letter.startswith("\\"):
        letter = LATEX_SYMBOLS.get(letter[1:], letter[1:])
    return unicodedata.normalize("NFC", letter.replace("ı", "i") + LATEX_ACCENTS[accent])


def _command(match):
    name, has_argument = match.group(1), match.group(2)
    if has_argument:
        return ""
    return LATEX_SYMBOLS.get(name, name)


def _script(match):
    marker, body = match.group(1), match.group(2) or match.group(3)
    converted = body.translate(SUPERSCRIPT if marker == "^" else SUBSCRIPT)
    if not any(c in converted for c in body):
        return converted
    return marker + (body if len(body) == 1 else f"({body})")


def _convert_latex(text):
    text = re.sub(r"\\(['`^\"~=.])\s*(\{\s*)?(\\[A-Za-z]+|\w)(?(2)\s*\})",
                  lambda m: _accent(m.group(1), m.group(3)), text)
    text = re.sub(r"\\([cvuHkr])(?:\s*\{\s*(\\[A-Za-z]+|\w)\s*\}|\s+(\w))",
                  lambda m: _accent(m.group(1), m.group(2) or m.group(3)), text)
    text = re.sub(r"\\([A-Za-z]+)\*?(?![A-Za-z])(\s*\{)?", lambda m: _command(m) + ("{" if m.group(2) else ""), text)
    return re.sub(r"([\^_])(?:\{([^{}]*)\}|(\w))", _script, text)


def _latex_to_text(text):
    placeholders = {}

    def protect(match):
        key = chr(0xE000 + len(placeholders))
        placeholders[key] = LATEX_ESCAPES[match.group(1)]
        return key

    text = re.sub(r"\\([&%_#${}])", protect, text)
    text = re.sub(r"\\\((.*?)\\\)|\\\[(.*?)\\\]", lambda m: _convert_latex(m.group(1) or m.group(2) or ""), text)
    if text.count("$") % 2 == 0:
        text = re.sub(r"\$([^$]*)\$", lambda m: _convert_latex(m.group(1)), text)
    text = _convert_latex(text)
    text = re.sub(r"\\[,;:! ]", " ", text).replace("{", "").replace("}", "").replace("\\", "")
    text = text.replace("``", "“").replace("''", "”").replace("'’", "”")
    text = re.sub(r"(?<=\w)`(?=\w)", "'", text).replace("`", "‘")
    text = re.sub(r'“([^"“”]*)"', r"“\1”", text)
    text = re.sub(r"‘([^'‘’]*)'", r"‘\1’", text)
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


def _text(value):
    text = str(value or "")
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = "".join(c for c in text if c in "\t\n " or unicodedata.category(c) not in {"Cc", "Cf"})
    if LATEX_MARKERS.search(text):
        text = _latex_to_text(text)
    return " ".join(text.split())


def _title_text(value):
    title = _text(value)
    if len(title) > 1 and QUOTE_PAIRS.get(title[0]) == title[-1] and title.count(title[0]) <= 2:
        title = title[1:-1].strip()
    elif title[:1] in QUOTE_PAIRS and QUOTE_PAIRS[title[0]] not in title[1:]:
        title = title[1:].strip()
    last_word = re.search(r"(\w+)\.$", title)
    if last_word and len(last_word.group(1)) > 1 and last_word.group(1).lower() not in ABBREVIATIONS:
        title = title[:-1]
    return title


def _http_url(value, base=""):
    if not isinstance(value, str) or not value.strip() or value.strip() == "None":
        return ""
    url = urljoin(base, value.strip())
    return url if urlparse(url).scheme in {"http", "https"} else ""


def _authors(names):
    return ", ".join(n for n in (_text(name).strip(" *,'\"‘’“”") for name in names) if n)


def _flip_name(name):
    last, _, first = name.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def _record(title, url, authors="", pdf_url=""):
    return {"title": _title_text(title), "url": url, "authors": authors, "pdf_url": pdf_url}


def _parse_miccai_json(body, source):
    records = []
    for item in json.loads(body):
        if not isinstance(item, dict):
            continue
        names = re.split(r"\s+and\s+", str(item.get("authors") or ""), flags=re.I)
        pdf_url = _http_url(item.get("pdflink"), source.url)
        records.append(_record(
            item.get("title"), pdf_url or _http_url(item.get("url"), source.url),
            authors=_authors(_flip_name(n) for n in names), pdf_url=pdf_url,
        ))
    return records


def _openreview_pdf(url):
    parsed = urlparse(url)
    if parsed.hostname not in {"openreview.net", "www.openreview.net"} or parsed.path != "/forum":
        return ""
    forum_id = parse_qs(parsed.query).get("id", [""])[0]
    return f"https://openreview.net/pdf?id={forum_id}" if forum_id else ""


def _parse_virtual_site_json(body, source):
    data = json.loads(body)
    items = data.get("results", []) if isinstance(data, dict) else data
    records = []
    for item in items:
        if not isinstance(item, dict):
            continue
        paper_url = _http_url(item.get("paper_url"))
        pdf_link = _http_url(item.get("paper_pdf_url"))
        is_pdf = pdf_link.lower().endswith(".pdf") or "/pdf" in urlparse(pdf_link).path
        url = paper_url or (pdf_link if not is_pdf else "") or _http_url(item.get("virtualsite_url"), source.url)
        records.append(_record(
            item.get("name"), url,
            authors=_authors(a.get("fullname") for a in item.get("authors") or [] if isinstance(a, dict)),
            pdf_url=(pdf_link if is_pdf else "") or _openreview_pdf(paper_url),
        ))
    return records


def _soup(body):
    return BeautifulSoup(body, "lxml")


def _parse_cvf_html(body, source):
    href_filter = source.options.get("href_contains", "")
    records = []
    for heading in _soup(body).select("dt.ptitle"):
        link = heading.find("a", href=True)
        if not link or (href_filter and href_filter not in link["href"]):
            continue
        authors_block = heading.find_next_sibling(["dd", "dt"])
        authors = ""
        if authors_block is not None and authors_block.name == "dd":
            authors = _authors(authors_block.get_text(" ", strip=True).split(","))
            links_block = authors_block.find_next_sibling(["dd", "dt"])
        else:
            links_block = None
        pdf = ""
        if links_block is not None and links_block.name == "dd":
            pdf_link = links_block.find(lambda tag: tag.name == "a" and tag.get_text(strip=True).lower() == "pdf")
            pdf = _http_url(pdf_link.get("href"), source.url) if pdf_link else ""
        records.append(_record(link.get_text(" ", strip=True), _http_url(link["href"], source.url), authors, pdf))
    return records


def _parse_html_selectors(body, source):
    options = source.options
    if not options.get("item"):
        raise ValueError('html_selectors needs an "item" CSS selector in options')
    records = []
    for item in _soup(body).select(options["item"]):
        title = item.select_one(options["title"]) if options.get("title") else item
        link = item.select_one(options.get("link") or "a[href]")
        authors = item.select_one(options["authors"]) if options.get("authors") else None
        pdf = item.select_one(options["pdf"]) if options.get("pdf") else None
        records.append(_record(
            title.get_text(" ", strip=True) if title else "",
            _http_url(link.get("href"), source.url) if link else "",
            authors=_authors(authors.get_text(" ", strip=True).split(",")) if authors else "",
            pdf_url=_http_url(pdf.get("href"), source.url) if pdf else "",
        ))
    return records


def _parse_html_links(body, source):
    href_filter = source.options.get("href_contains", "")
    records = []
    for link in _soup(body).find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        if (href_filter and href_filter not in link["href"]) or not (
                MIN_LINK_TITLE_WORDS <= len(title.split()) <= MAX_LINK_TITLE_WORDS):
            continue
        records.append(_record(title, _http_url(link["href"], source.url)))
    return records


PARSERS = {
    "miccai_json": _parse_miccai_json,
    "virtual_site_json": _parse_virtual_site_json,
    "cvf_html": _parse_cvf_html,
    "html_selectors": _parse_html_selectors,
    "html_links": _parse_html_links,
}


def _clean_records(records):
    seen, papers = set(), []
    for record in records:
        title = _clean_title(record["title"])
        key = normalize_title(title)
        url, pdf_url = _http_url(record["url"]), _http_url(record["pdf_url"])
        if (len(title) < MIN_TITLE_CHARS or not url or key in seen
                or len(url) > URL_MAX or len(key) > TITLE_MAX):
            continue
        seen.add(key)
        papers.append(dict(record, title=title[:TITLE_MAX], normalized_title=key, url=url,
                           pdf_url=pdf_url if len(pdf_url) <= URL_MAX else ""))
    return papers


def _finish(source, status, message, count=None):
    source.last_synced_at = timezone.now()
    source.last_status = status
    source.last_message = message[:500]
    fields = ["last_synced_at", "last_status", "last_message"]
    if count is not None:
        source.paper_count = count
        fields.append("paper_count")
    source.save(update_fields=fields)
    log = logger.info if status == "ok" else logger.warning
    log("Proceedings sync %s (%s): %s", source, source.url, message)
    return status


def sync_source(source):
    parser = PARSERS.get(source.parser)
    if parser is None:
        return _finish(source, "error", f"Unknown parser {source.parser!r}")
    body, content_type = _download_capped(source.url, MAX_DOWNLOAD_BYTES, DOWNLOAD_TIMEOUT, ACCEPTED_TYPES)
    if body is None:
        return _finish(source, "error", f"Download failed or unsupported content ({content_type or 'no response'})")
    try:
        papers = _clean_records(parser(body, source))
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        return _finish(source, "error", f"Parse failed: {type(exc).__name__}: {exc}")
    if not papers:
        return _finish(source, "empty", "No papers found; kept the previous list")
    with transaction.atomic():
        ProceedingsPaper.objects.filter(source=source).delete()
        ProceedingsPaper.objects.bulk_create(
            [ProceedingsPaper(source=source, **paper) for paper in papers], batch_size=1000,
        )
    return _finish(source, "ok", f"{len(papers)} papers", count=len(papers))


def sync_sources(source_ids=None):
    sources = ProceedingsSource.objects.filter(enabled=True)
    if source_ids:
        sources = sources.filter(pk__in=source_ids)
    results = {}
    for source in sources:
        lock = f"proceedings-sync:{source.pk}"
        if not cache.add(lock, True, timeout=SYNC_LOCK_TTL):
            results[str(source)] = "busy"
            continue
        try:
            results[str(source)] = sync_source(source)
        finally:
            cache.delete(lock)
    return results
