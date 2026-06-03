"""Test per i parser Tree-sitter multilanguage (Fase 3).

Tutto il modulo viene skippato se la dipendenza opzionale [multilang]
(tree-sitter-language-pack) non è installata.
"""

import pytest

pytest.importorskip(
    "tree_sitter_language_pack",
    reason="tree-sitter-language-pack non installato — "
    "esegui pip install 'intelligence-suite[multilang]'",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def ts_file(tmp_path):
    code = """
function authenticate(userId: string, token: string): boolean {
    const result = verifyToken(token);
    logAccess(userId);
    return result;
}

const getUser = (id: string) => {
    return fetchUser(id);
};
"""
    p = tmp_path / "auth.ts"
    p.write_text(code)
    return p


@pytest.fixture()
def go_file(tmp_path):
    code = """
package main

func verifyToken(token string) bool {
    decoded := decodeJWT(token)
    return checkExpiry(decoded)
}

func loginHandler(w int) {
    token := "x"
    verifyToken(token)
}
"""
    p = tmp_path / "auth.go"
    p.write_text(code)
    return p


@pytest.fixture()
def java_file(tmp_path):
    code = """
public class AuthService {
    public boolean verifyToken(String token) {
        String decoded = decodeJWT(token);
        return checkExpiry(decoded);
    }

    public User getUser(String id) {
        return userRepository.findById(id);
    }
}
"""
    p = tmp_path / "AuthService.java"
    p.write_text(code)
    return p


@pytest.fixture()
def rust_file(tmp_path):
    code = """
fn verify(token: &str) -> bool {
    check(decode(token))
}

impl Foo {
    fn bar(&self) {
        baz();
    }
}
"""
    p = tmp_path / "lib.rs"
    p.write_text(code)
    return p


# ── TypeScript ──────────────────────────────────────────────────────────────

def test_typescript_parser_finds_functions(ts_file):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    chunks = TypeScriptParser().parse_file(ts_file)
    assert len(chunks) >= 1


def test_typescript_parser_extracts_name(ts_file):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    chunks = TypeScriptParser().parse_file(ts_file)
    names = [c["metadata"]["name"] for c in chunks]
    assert "authenticate" in names


def test_typescript_parser_extracts_calls(ts_file):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    chunks = TypeScriptParser().parse_file(ts_file)
    auth = next(c for c in chunks if c["metadata"]["name"] == "authenticate")
    calls = auth["metadata"]["calls"]
    assert "verifyToken" in calls or "logAccess" in calls


def test_typescript_parser_chunk_format(ts_file):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    chunks = TypeScriptParser().parse_file(ts_file)
    for chunk in chunks:
        assert "id" in chunk
        assert "text" in chunk
        assert "type" in chunk
        assert "source" in chunk
        assert "metadata" in chunk
        assert "name" in chunk["metadata"]
        assert "line" in chunk["metadata"]
        assert "calls" in chunk["metadata"]


def test_typescript_parser_empty_file(tmp_path):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    empty = tmp_path / "empty.ts"
    empty.write_text("")
    assert TypeScriptParser().parse_file(empty) == []


def test_typescript_parser_invalid_bytes(tmp_path):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    bad = tmp_path / "bad.ts"
    bad.write_bytes(b"\xff\xfe invalid")
    chunks = TypeScriptParser().parse_file(bad)
    assert isinstance(chunks, list)


# ── Go ──────────────────────────────────────────────────────────────────────

def test_go_parser_finds_functions(go_file):
    from intelligence_core.parsers.go_parser_ts import GoParser
    assert len(GoParser().parse_file(go_file)) >= 1


def test_go_parser_extracts_name(go_file):
    from intelligence_core.parsers.go_parser_ts import GoParser
    names = [c["metadata"]["name"] for c in GoParser().parse_file(go_file)]
    assert "verifyToken" in names or "loginHandler" in names


def test_go_parser_extracts_calls(go_file):
    from intelligence_core.parsers.go_parser_ts import GoParser
    chunks = GoParser().parse_file(go_file)
    vt = next(c for c in chunks if c["metadata"]["name"] == "verifyToken")
    assert "decodeJWT" in vt["metadata"]["calls"]


def test_go_parser_chunk_language(go_file):
    from intelligence_core.parsers.go_parser_ts import GoParser
    for chunk in GoParser().parse_file(go_file):
        assert chunk["metadata"]["language"] == "go"


# ── Java ──────────────────────────────────────────────────────────────────────

def test_java_parser_finds_methods(java_file):
    from intelligence_core.parsers.java_parser_ts import JavaParser
    assert len(JavaParser().parse_file(java_file)) >= 1


def test_java_parser_extracts_name(java_file):
    from intelligence_core.parsers.java_parser_ts import JavaParser
    names = [c["metadata"]["name"] for c in JavaParser().parse_file(java_file)]
    assert "verifyToken" in names or "getUser" in names


def test_java_parser_extracts_calls(java_file):
    from intelligence_core.parsers.java_parser_ts import JavaParser
    chunks = JavaParser().parse_file(java_file)
    vt = next(c for c in chunks if c["metadata"]["name"] == "verifyToken")
    assert "decodeJWT" in vt["metadata"]["calls"]


# ── Rust ──────────────────────────────────────────────────────────────────────

def test_rust_parser_finds_functions(rust_file):
    from intelligence_core.parsers.rust_parser_ts import RustParser
    names = [c["metadata"]["name"] for c in RustParser().parse_file(rust_file)]
    assert "verify" in names and "bar" in names


def test_rust_parser_extracts_calls(rust_file):
    from intelligence_core.parsers.rust_parser_ts import RustParser
    chunks = RustParser().parse_file(rust_file)
    verify = next(c for c in chunks if c["metadata"]["name"] == "verify")
    assert "check" in verify["metadata"]["calls"]


# ── BaseParser interface ──────────────────────────────────────────────────────

def test_can_parse_correct_extension(ts_file):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    assert TypeScriptParser().can_parse(ts_file) is True


def test_can_parse_wrong_extension(tmp_path):
    from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
    assert TypeScriptParser().can_parse(tmp_path / "file.py") is False


def test_missing_file_returns_empty(tmp_path):
    from intelligence_core.parsers.go_parser_ts import GoParser
    assert GoParser().parse_file(tmp_path / "nope.go") == []


# ── Il parser Python esistente resta intatto (module-based, non toccato) ───────

def test_existing_python_parser_still_works(tmp_path):
    from CodeIntelligence.parsers import python_parser
    py_file = tmp_path / "test.py"
    py_file.write_text("def hello(name: str) -> str:\n    return f'Hello {name}'\n")
    chunks = python_parser.parse_file(py_file, tmp_path)
    assert len(chunks) >= 1
    names = [c.get("metadata", {}).get("name") for c in chunks]
    assert "hello" in names
