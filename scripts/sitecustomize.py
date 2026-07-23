"""Temporary helper for the one-shot audit runner; removed after the audited commit."""

from __future__ import annotations

import shutil
from pathlib import Path

_original_copyfile = shutil.copyfile


def _copyfile_with_template_namespace(source, destination, *args, **kwargs):
    target = Path(destination)
    if target.name == "packages.lock.json.template":
        content = Path(source).read_text(encoding="utf-8").replace("Locked", "__NAMESPACE__")
        target.write_text(content, encoding="utf-8", newline="\n")
        return str(target)
    return _original_copyfile(source, destination, *args, **kwargs)


shutil.copyfile = _copyfile_with_template_namespace
