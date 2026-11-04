"""Conservative static import closure, including imports inside dormant LiDAR branches."""

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    roots = ['main', 'qt_main', 'acquisition_api', 'deployment_check']
    seen, pending = set(), roots[:]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = root / (name.replace('.', '/') + '.py')
        if not path.exists():
            path = root / name.replace('.', '/') / '__init__.py'
        if not path.exists():
            continue
        seen.add(name)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(module for module in imports if module.startswith(('model.', 'control.', 'view.')) or module in ('app_bootstrap',))
    retained = {str((root / name.replace('.', '/')).relative_to(root)).replace('\\', '/') + '.py'
                for name in seen if name.startswith('model.')}
    # All package initializers are retained; code inside any branch of the two protected files counts.
    unused = [str(p.relative_to(root)).replace('\\', '/') for p in sorted((root / 'model').rglob('*.py'))
              if p.name != '__init__.py' and '__pycache__' not in p.parts and str(p.relative_to(root)).replace('\\', '/') not in retained]
    return {'retained_modules': sorted(retained), 'unused_python_files': unused}


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
