import html
import re
import unicodedata


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


def clean_text(value):
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


def clean_title(value):
    title = clean_text(value)
    if len(title) > 1 and QUOTE_PAIRS.get(title[0]) == title[-1] and title.count(title[0]) <= 2:
        title = title[1:-1].strip()
    elif title[:1] in QUOTE_PAIRS and QUOTE_PAIRS[title[0]] not in title[1:]:
        title = title[1:].strip()
    last_word = re.search(r"(\w+)\.$", title)
    if last_word and len(last_word.group(1)) > 1 and last_word.group(1).lower() not in ABBREVIATIONS:
        title = title[:-1]
    return title
