"""Registry dei parser CodeIntelligence."""

from pathlib import Path

_PARSERS = []


def _load_parsers():
    from . import python_parser
    _PARSERS.append(python_parser)
    # Tree-sitter (opzionale, extra [multilang]): se disponibile gestisce
    # TS/Go/Java/Rust con parsing strutturale preciso e ha la precedenza sui
    # parser regex sottostanti. Se l'import fallisce si ricade sui regex.
    try:
        from . import treesitter_adapter
        _PARSERS.append(treesitter_adapter)
    except Exception:
        pass
    try:
        from . import typescript_parser
        _PARSERS.append(typescript_parser)
    except Exception:
        pass
    try:
        from . import go_parser
        _PARSERS.append(go_parser)
    except Exception:
        pass
    try:
        from . import yaml_parser
        _PARSERS.append(yaml_parser)
    except Exception:
        pass
    try:
        from . import markdown_parser
        _PARSERS.append(markdown_parser)
    except Exception:
        pass
    try:
        from . import sql_parser
        _PARSERS.append(sql_parser)
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


def register_parser(parser_module) -> None:
    """Registra un parser esterno nel registry."""
    if not _PARSERS:
        _load_parsers()
    _PARSERS.insert(0, parser_module)
