"""Keep the existing Cython build workflow; do not generate files inside model/."""

from pathlib import Path
import sys
from tools.linux_compat import prepare_linux_source
from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize
from tools.export_developer_package import protected_modules


ROOT = Path(__file__).resolve().parent
extensions = [Extension(module, [(prepare_linux_source(ROOT, source) if sys.platform.startswith("linux") else source).relative_to(ROOT).as_posix()])
              for module, source in protected_modules(ROOT)]

setup(
    name='robot-cal',
    version='1.0.0',
    python_requires='>=3.11',
    packages=find_packages(include=['control', 'control.*', 'model', 'model.*', 'view', 'view.*']),
    package_data={'model.tomls': ['*.toml']},
    ext_modules=cythonize(extensions, language_level=3, build_dir='build/cython', force=True),
    zip_safe=False,
)
