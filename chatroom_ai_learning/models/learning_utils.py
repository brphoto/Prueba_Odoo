# -*- coding: utf-8 -*-
"""Comparación de textos sin dependencias externas."""
import difflib
import re
import unicodedata

STOPWORDS = {
    'a', 'al', 'algo', 'con', 'de', 'del', 'el', 'en', 'es', 'esta', 'este', 'la', 'las',
    'le', 'lo', 'los', 'me', 'mi', 'muy', 'no', 'o', 'para', 'pero', 'por', 'que', 'se',
    'si', 'su', 'sus', 'te', 'tu', 'un', 'una', 'y', 'ya', 'hola', 'buenas', 'gracias',
}

CATEGORIES = [
    ('consulta', 'Consulta'),
    ('venta', 'Venta'),
    ('soporte', 'Soporte'),
    ('queja', 'Queja'),
    ('otro', 'Otro'),
]


def normalize(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def tokens(text):
    return {word for word in normalize(text).split() if len(word) > 2 and word not in STOPWORDS}


def keyword_overlap(query, candidate):
    """Parecido temático entre dos mensajes (0-1)."""
    first, second = tokens(query), tokens(candidate)
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def text_similarity(first, second):
    """Parecido entre dos respuestas (0-1), tolerante a mayúsculas y signos."""
    first, second = normalize(first), normalize(second)
    if not first or not second:
        return 0.0
    return difflib.SequenceMatcher(None, first, second).ratio()


def contains_phrase(text, phrase):
    """La frase aparece como palabras completas en el texto."""
    phrase = normalize(phrase)
    return bool(phrase) and re.search(r'(^| )%s( |$)' % re.escape(phrase), normalize(text)) is not None


def split_list(value):
    return [item.strip() for item in re.split(r'[\n,;]+', value or '') if item.strip()]
