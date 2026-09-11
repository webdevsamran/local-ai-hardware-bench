"""Text-to-SQL scored by what the query returns, not by how it is spelled.

String-matching a generated query against a reference is the wrong measurement
and it is the easy one. `SELECT name FROM t WHERE age > 30` and
`SELECT t.name FROM t WHERE 30 < t.age` are the same query and differ in every
character that matters to a string comparison, so a text metric reports a
correct model as wrong and rewards one that happens to imitate the reference's
formatting.

Execution accuracy -- run both, compare what comes back -- is what Spider and
its successors use, and it is what this measures.

Three decisions that make the number mean something:

**Row order matters only when the reference asked for it.** A query with no
`ORDER BY` returns rows in whatever order the engine chose, so comparing
ordered sequences would fail correct answers at random. With `ORDER BY` the
order *is* part of the answer and is compared.

**A query that fails to execute is wrong, not unmeasurable.** Invalid SQL is a
wrong answer -- unlike an unreadable multiple-choice response, there is no
ambiguity about what the model produced. But a *reference* that fails to
execute is a broken dataset row, and that scores None: the fault is not the
model's.

**The database is opened read-only.** The SQL being executed was written by a
model, and a benchmark that runs `DROP TABLE` because a model emitted it is a
benchmark that destroys its own fixtures. SQLite's read-only URI mode enforces
this at the connection rather than by pattern-matching the query, because
pattern-matching statements is a game you lose.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime only
    from .evaluators import EvaluatorScore

__all__ = [
    "execute_query",
    "compare_sql_results",
    "SqlExecutionEvaluator",
    "DEFAULT_QUERY_TIMEOUT_SECONDS",
]

#: Wall-clock ceiling for one query. A model can emit a cross join over three
#: tables that never finishes; the benchmark must not hang on it, and a query
#: that cannot complete is not a correct answer.
DEFAULT_QUERY_TIMEOUT_SECONDS = 30.0


def _connect_read_only(database: str | Path) -> sqlite3.Connection:
    """Open a database that cannot be written, whatever the query says.

    Enforced by SQLite rather than by inspecting the SQL: a denylist of
    keywords is defeated by comments, casing, and statements nobody thought
    of, and the cost of being wrong is a destroyed fixture.
    """
    path = Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"no database at {path}")
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=DEFAULT_QUERY_TIMEOUT_SECONDS)


def execute_query(
    database: str | Path,
    sql: str,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run one query read-only and return its rows, or why it did not run."""
    statements = [s for s in sql.split(";") if s.strip()]
    if len(statements) > 1:
        # Not a safety control -- the connection is read-only -- but a
        # correctness one: "which statement's result is the answer?" has no
        # good answer, and running only the first would score a model on a
        # query it did not mean.
        return {"rows": None, "error": "more than one statement; a single query is expected"}

    try:
        connection = _connect_read_only(database)
    except (FileNotFoundError, sqlite3.Error) as exc:
        return {"rows": None, "error": f"database could not be opened: {exc}"}

    try:
        connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
        cursor = connection.execute(sql)
        return {"rows": cursor.fetchall(), "error": None}
    except sqlite3.Error as exc:
        return {"rows": None, "error": str(exc)}
    finally:
        connection.close()


def _ordered(sql: str) -> bool:
    """Whether the reference query asked for a particular row order."""
    return "order by" in " ".join(sql.lower().split())


def _comparable(rows: list[tuple[Any, ...]], ordered: bool) -> Any:
    if ordered:
        return [tuple(row) for row in rows]
    # A multiset, not a set: `SELECT city FROM t` returning London twice is a
    # different answer from returning it once, and collapsing duplicates would
    # score a wrong `DISTINCT` as correct.
    return sorted(tuple(str(value) for value in row) for row in rows)


def compare_sql_results(
    database: str | Path,
    predicted_sql: str,
    reference_sql: str,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execution accuracy for one query pair: 1.0, 0.0, or None.

    None means the question could not be asked -- a missing database or a
    reference that does not run. Those are faults in the dataset, and charging
    them to the model would make a broken fixture look like a bad model.
    """
    reference = execute_query(database, reference_sql, timeout_seconds)
    if reference["error"] is not None:
        return {
            "score": None,
            "detail": f"the reference query did not execute: {reference['error']}",
            "reference_error": reference["error"],
        }

    predicted = execute_query(database, predicted_sql, timeout_seconds)
    if predicted["error"] is not None:
        # Invalid SQL is a wrong answer. There is no ambiguity about what the
        # model produced, unlike an unreadable free-text response.
        return {
            "score": 0.0,
            "detail": f"the predicted query did not execute: {predicted['error']}",
            "predicted_error": predicted["error"],
        }

    ordered = _ordered(reference_sql)
    matches = _comparable(predicted["rows"], ordered) == _comparable(reference["rows"], ordered)
    return {
        "score": 1.0 if matches else 0.0,
        "detail": None
        if matches
        else (
            f"returned {len(predicted['rows'])} row(s) where the reference "
            f"returned {len(reference['rows'])}"
            if len(predicted["rows"]) != len(reference["rows"])
            else "returned the same number of rows with different contents"
        ),
        "order_significant": ordered,
        "predicted_error": None,
        "reference_error": None,
    }


class SqlExecutionEvaluator:
    """Execution accuracy, as an evaluator over a JSONL dataset.

    Spider asks each question against a *different* database, so the expected
    value may name one:

        {"input": "...", "expected": {"db": "concert.sqlite", "sql": "SELECT ..."}}

    A plain string expected value is treated as the reference SQL against the
    evaluator's configured default database, for single-database sets.
    """

    name = "sql_execution"

    def __init__(self, database: str | Path | None = None) -> None:
        self.database = database

    def evaluate(self, response: str, expected: str | None = None) -> EvaluatorScore:
        from .evaluators import EvaluatorScore

        if expected is None:
            return EvaluatorScore(self.name, None, "no reference query supplied")

        database = self.database
        reference_sql = expected
        if expected.lstrip().startswith("{"):
            try:
                spec = json.loads(expected)
            except json.JSONDecodeError as exc:
                return EvaluatorScore(self.name, None, f"malformed expected value: {exc}")
            reference_sql = spec.get("sql") or ""
            database = spec.get("db") or database

        if not database:
            return EvaluatorScore(
                self.name,
                None,
                "no database: give the evaluator one, or name it per row as "
                '{"db": ..., "sql": ...}',
            )
        if not reference_sql.strip():
            return EvaluatorScore(self.name, None, "the reference query is empty")

        outcome = compare_sql_results(database, response, reference_sql)
        return EvaluatorScore(self.name, outcome["score"], outcome["detail"])
