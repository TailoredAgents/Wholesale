import ast
from pathlib import Path

MIGRATIONS = Path(__file__).parents[1] / "alembic" / "versions"
ALEMBIC_VERSION_NUM_MAX_LENGTH = 32


def migration_revision(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "revision"
            and isinstance(node.value, ast.Constant)
        ):
            assert isinstance(node.value.value, str)
            return node.value.value
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "revision"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
        ):
            assert isinstance(node.value.value, str)
            return node.value.value
    raise AssertionError(f"Migration {path.name} does not declare a literal revision ID.")


def test_alembic_revision_ids_fit_the_version_table() -> None:
    revisions = {
        path.name: migration_revision(path)
        for path in sorted(MIGRATIONS.glob("*.py"))
        if path.name != "__init__.py"
    }

    too_long = {
        filename: revision
        for filename, revision in revisions.items()
        if len(revision) > ALEMBIC_VERSION_NUM_MAX_LENGTH
    }
    assert not too_long, (
        "Alembic stores revision IDs in alembic_version.version_num VARCHAR(32); "
        f"shorten these IDs: {too_long}"
    )
    assert len(set(revisions.values())) == len(revisions), "Alembic revision IDs must be unique."
