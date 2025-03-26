from importlib.metadata import entry_points

from pathlib import Path
from typing import Iterable


class ProjectsRoot:
    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)

    def list_projects(self) -> Iterable[Path]:
        if not self.root_dir.exists() or not self.root_dir.is_dir():
            return []
        for p in self.root_dir.iterdir():
            if p.is_dir():
                yield p


_ROOTS = [
    ProjectsRoot(Path("~/ai-migrator-projects").expanduser()),
]
_EXTRA_ROOTS_LOADED = False


def _load_roots():
    global _EXTRA_ROOTS_LOADED
    for ep in entry_points(group="ai_migrate").select(name="projects_root"):
        roots = ep.load()
        if hasattr(roots, "__iter__"):
            _ROOTS.extend(roots)
        else:
            _ROOTS.append(roots)
    _EXTRA_ROOTS_LOADED = True


def get_project_dir(name: str) -> Path:
    if not _EXTRA_ROOTS_LOADED:
        _load_roots()
    for root in _ROOTS:
        for project in root.list_projects():
            if project.name == name:
                return project
    raise FileNotFoundError(
        f"Project {name} not found in project roots [{', '.join(str(r.root_dir) for r in _ROOTS)}]"
    )
