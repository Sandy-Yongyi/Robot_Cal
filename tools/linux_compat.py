"""Linux build-only adaptation of legacy path literals; source files stay intact."""
import io
import tokenize
from pathlib import Path


def linux_source_text(source):
    tokens = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        text = token.string
        if token.type == tokenize.STRING and ('toml' in text.lower() or 'data' in text.lower()):
            text = text.replace('\\\\', '/')
        tokens.append(token._replace(string=text))
    return tokenize.untokenize(tokens)


def prepare_linux_source(root, source):
    root, source = Path(root), Path(source)
    target = root / 'build/linux-source' / source.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(linux_source_text(source.read_text(encoding='utf-8-sig')), encoding='utf-8')
    return target
