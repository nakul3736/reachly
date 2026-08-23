"""Every model module must be imported by `app/models/__init__.py`.

This test exists because of a real failure the rest of the suite could not see.

`MatchScore` and `TailoredResume` were written and used, but never added to the imports in
`app/models/__init__.py`. Autogenerate compares the database against `Base.metadata`, and a model
absent from that metadata is absent from both sides of the comparison — so it produced two
migrations whose bodies were `pass`, and `alembic check` reported no pending changes with complete
confidence.

Every other test still passed, because the test fixture creates the schema with
`metadata.create_all()` after the test module has imported the models directly, while deployment
creates it with `alembic upgrade head`. Those two paths disagreed and only the deployed application
knew: the scored feed raised `relation "match_scores" does not exist`, which the browser reported
as "Failed to fetch".

**The first version of this test was itself useless, and the control run proved it.** It compared
model modules against `Base.metadata`, which is global and accumulative — once any module imports a
class, the table stays registered for the life of the process, so deleting the import from
`__init__.py` changed nothing and the test still passed. Reading the import statements is the only
check that cannot be satisfied accidentally by another test's imports.
"""

import ast
import pkgutil
from pathlib import Path

import app.models


def _model_modules_defining_tables() -> set[str]:
    """Module names under app/models that declare at least one mapped table.

    Read from source rather than imported, so this cannot be influenced by whatever else the test
    session has already loaded.
    """
    package_dir = Path(app.models.__path__[0])
    defining: set[str] = set()

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        source = (package_dir / f"{module_info.name}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # A mapped class sets __tablename__.
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign | ast.Assign):
                    targets = (
                        [statement.target]
                        if isinstance(statement, ast.AnnAssign)
                        else statement.targets
                    )
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id == "__tablename__":
                            defining.add(module_info.name)

    return defining


def _modules_imported_by_the_package() -> set[str]:
    package_init = Path(app.models.__path__[0]) / "__init__.py"
    tree = ast.parse(package_init.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.models.")
        ):
            imported.add(node.module.removeprefix("app.models."))
    return imported


def test_every_model_module_is_imported_by_the_package() -> None:
    defining = _model_modules_defining_tables()
    imported = _modules_imported_by_the_package()

    missing = sorted(defining - imported)

    assert missing == [], (
        "these modules define tables but are not imported in app/models/__init__.py, so Alembic "
        "autogenerate cannot see them and will write an empty migration that passes every test "
        f"and fails only in the deployed app: {missing}"
    )


def test_the_check_has_something_to_check() -> None:
    """Guards the guard: if the AST walk stopped finding models, the test above would pass
    vacuously and silently stop protecting anything."""
    defining = _model_modules_defining_tables()

    assert len(defining) >= 5, f"only found {defining}, which means the detection is broken"
    assert "job" in defining
    assert "match_score" in defining
