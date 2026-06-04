"""Registry dei parser DocIntelligence."""

from pathlib import Path

_PARSERS = []


def _load_parsers():
    try:
        from . import pdf_parser
        _PARSERS.append(pdf_parser)
    except Exception:
        pass
    try:
        from . import docx_parser
        _PARSERS.append(docx_parser)
    except Exception:
        pass
    try:
        from . import xlsx_parser
        _PARSERS.append(xlsx_parser)
    except Exception:
        pass
    try:
        from . import markdown_parser
        _PARSERS.append(markdown_parser)
    except Exception:
        pass
    try:
        from . import csv_parser
        _PARSERS.append(csv_parser)
    except Exception:
        pass
    try:
        from . import txt_parser
        _PARSERS.append(txt_parser)
    except Exception:
        pass


def get_parser(path: Path):
    """Ritorna il primo parser che sa gestire questo file, o None."""
    if not _PARSERS:
        _load_parsers()
    for parser in _PARSERS:
        if parser.can_parse(path):
            return parser
    return None
