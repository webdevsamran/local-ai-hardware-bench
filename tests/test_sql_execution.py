"""Text-to-SQL is scored by what the query returns, not how it is spelled.

`SELECT name FROM t WHERE age > 30` and `SELECT t.name FROM t WHERE 30 < t.age`
are the same query. A string metric calls the second one wrong, which reports a
correct model as incorrect and rewards a model that imitates the reference's
formatting. Execution accuracy is what Spider uses and what this measures.
"""

from __future__ import annotations

import sqlite3

import pytest

from aihwbench.sql_execution import compare_sql_results, execute_query

REFERENCE = "SELECT name FROM people WHERE age > 40"


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "people.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE people (name TEXT, age INT, city TEXT);
        INSERT INTO people VALUES ('Ada', 36, 'London');
        INSERT INTO people VALUES ('Grace', 45, 'NYC');
        INSERT INTO people VALUES ('Alan', 41, 'London');
        """
    )
    connection.commit()
    connection.close()
    return path


# --- the point of execution accuracy ---------------------------------------


def test_an_equivalent_query_spelled_differently_is_correct(database):
    """The measurement a string metric gets wrong."""
    assert (
        compare_sql_results(database, "SELECT p.name FROM people p WHERE 40 < p.age", REFERENCE)[
            "score"
        ]
        == 1.0
    )


def test_an_identical_query_is_correct(database):
    assert compare_sql_results(database, REFERENCE, REFERENCE)["score"] == 1.0


def test_a_query_returning_different_rows_is_wrong(database):
    outcome = compare_sql_results(database, "SELECT name FROM people WHERE age > 30", REFERENCE)
    assert outcome["score"] == 0.0
    assert "3 row(s)" in outcome["detail"]


def test_row_order_is_ignored_when_the_reference_did_not_ask_for_it(database):
    """Without ORDER BY the engine may return rows in any order.

    Comparing sequences would fail correct answers for a reason that has
    nothing to do with the model.
    """
    outcome = compare_sql_results(
        database,
        "SELECT name FROM people WHERE age > 40 ORDER BY name DESC",
        REFERENCE,
    )
    assert outcome["score"] == 1.0
    assert outcome["order_significant"] is False


def test_row_order_is_compared_when_the_reference_asked_for_it(database):
    """With ORDER BY the order is part of the answer."""
    ordered_reference = "SELECT name FROM people WHERE age > 40 ORDER BY age ASC"
    same = compare_sql_results(database, ordered_reference, ordered_reference)
    reversed_order = compare_sql_results(
        database,
        "SELECT name FROM people WHERE age > 40 ORDER BY age DESC",
        ordered_reference,
    )
    assert same["score"] == 1.0
    assert same["order_significant"] is True
    assert reversed_order["score"] == 0.0


def test_duplicate_rows_are_not_collapsed(database):
    """A wrong DISTINCT must not score as correct.

    Comparing sets rather than multisets would make `SELECT DISTINCT city`
    indistinguishable from `SELECT city`, and they are different answers.
    """
    outcome = compare_sql_results(
        database, "SELECT DISTINCT city FROM people", "SELECT city FROM people"
    )
    assert outcome["score"] == 0.0


# --- what is the model's fault and what is not -----------------------------


def test_invalid_sql_is_a_wrong_answer(database):
    """Unlike an unreadable free-text response, there is no ambiguity here."""
    outcome = compare_sql_results(database, "SELECT nope FROM people", REFERENCE)
    assert outcome["score"] == 0.0
    assert "did not execute" in outcome["detail"]


def test_a_broken_reference_is_not_charged_to_the_model(database):
    """A dataset row that does not run is a fault in the dataset.

    Scoring it zero would make a broken fixture look like a bad model, and the
    error would be invisible in an aggregate.
    """
    outcome = compare_sql_results(database, REFERENCE, "SELECT * FROM no_such_table")
    assert outcome["score"] is None
    assert "reference query did not execute" in outcome["detail"]


def test_a_missing_database_is_not_charged_to_the_model(tmp_path):
    outcome = compare_sql_results(tmp_path / "absent.sqlite", REFERENCE, REFERENCE)
    assert outcome["score"] is None


# --- executing model-written SQL safely ------------------------------------


def test_a_write_is_refused_and_the_fixture_survives(database):
    """The SQL came from a model. A benchmark that drops its own tables
    because a model emitted `DROP TABLE` is not one you can run twice."""
    outcome = execute_query(database, "DELETE FROM people")
    assert outcome["error"] is not None
    assert "readonly" in outcome["error"].lower()
    assert execute_query(database, "SELECT COUNT(*) FROM people")["rows"] == [(3,)]


def test_a_drop_is_refused_and_the_table_survives(database):
    execute_query(database, "DROP TABLE people")
    assert execute_query(database, "SELECT COUNT(*) FROM people")["rows"] == [(3,)]


def test_more_than_one_statement_is_refused(database):
    """Not a safety control -- the connection is read-only -- but a
    correctness one: which statement's result would be the answer?"""
    outcome = execute_query(database, "SELECT name FROM people; SELECT age FROM people")
    assert outcome["rows"] is None
    assert "more than one statement" in outcome["error"]


def test_a_trailing_semicolon_is_not_two_statements(database):
    assert execute_query(database, "SELECT name FROM people;")["error"] is None


# --- the evaluator ----------------------------------------------------------


def test_the_evaluator_reads_a_per_row_database(database):
    """Spider asks each question against a different database."""
    import json

    from aihwbench.evaluators import get_evaluator

    evaluator = get_evaluator("sql_execution")
    expected = json.dumps({"db": str(database), "sql": REFERENCE})
    assert evaluator.evaluate(REFERENCE, expected).score == 1.0


def test_the_evaluator_says_so_when_no_database_is_named(database):
    from aihwbench.evaluators import get_evaluator

    result = get_evaluator("sql_execution").evaluate(REFERENCE, REFERENCE)
    assert result.score is None
    assert "no database" in (result.detail or "")


def test_the_evaluator_accepts_a_configured_default_database(database):
    from aihwbench.sql_execution import SqlExecutionEvaluator

    evaluator = SqlExecutionEvaluator(database)
    assert evaluator.evaluate(REFERENCE, REFERENCE).score == 1.0


def test_it_is_registered():
    from aihwbench.evaluators import list_evaluators

    assert "sql_execution" in list_evaluators()
