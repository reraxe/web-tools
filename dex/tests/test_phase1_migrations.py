import shutil
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from dex_migrations import Migration, MigrationError, apply_migrations


@contextmanager
def database(path: Path):
    connection = sqlite3.connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_legacy_fixture(path: Path) -> None:
    with database(path) as connection:
        connection.execute(
            "CREATE TABLE legacy_inventory (id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE)"
        )
        connection.execute("INSERT INTO legacy_inventory (sku) VALUES ('LEGACY-001')")


class TransactionalMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.legacy_source = self.root / "legacy-source.db"
        create_legacy_fixture(self.legacy_source)

    def tearDown(self):
        self.temp.cleanup()

    def copy_legacy_fixture(self, name: str) -> Path:
        destination = self.root / name
        shutil.copy2(self.legacy_source, destination)
        return destination

    def test_migration_runs_once_on_disposable_legacy_copy(self):
        working_copy = self.copy_legacy_fixture("working-success.db")
        calls = []

        def add_reference(connection):
            calls.append("applied")
            connection.execute("ALTER TABLE legacy_inventory ADD COLUMN reference TEXT")

        migration = Migration("0001_test_reference", "test legacy reference", add_reference)
        with database(working_copy) as connection:
            self.assertEqual(apply_migrations(connection, [migration]), ("0001_test_reference",))
            self.assertEqual(apply_migrations(connection, [migration]), ())
            columns = {row[1] for row in connection.execute("PRAGMA table_info(legacy_inventory)")}
            markers = connection.execute(
                "SELECT migration_id FROM schema_migrations"
            ).fetchall()
        self.assertEqual(calls, ["applied"])
        self.assertIn("reference", columns)
        self.assertEqual(markers, [("0001_test_reference",)])

        with database(self.legacy_source) as untouched:
            source_tables = {
                row[0] for row in untouched.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertNotIn("schema_migrations", source_tables)

    def test_failed_migration_rolls_back_schema_and_completion_marker(self):
        working_copy = self.copy_legacy_fixture("working-failure.db")

        def fail_after_schema_change(connection):
            connection.execute("CREATE TABLE should_rollback (id INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO should_rollback (id) VALUES (1)")
            raise RuntimeError("simulated migration failure")

        migration = Migration("0002_test_failure", "test rollback", fail_after_schema_change)
        with database(working_copy) as connection:
            with self.assertRaises(MigrationError):
                apply_migrations(connection, [migration])
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            markers = connection.execute(
                "SELECT migration_id FROM schema_migrations WHERE migration_id = ?",
                (migration.migration_id,),
            ).fetchall()
            legacy_row = connection.execute(
                "SELECT sku FROM legacy_inventory WHERE id = 1"
            ).fetchone()
        self.assertNotIn("should_rollback", tables)
        self.assertEqual(markers, [])
        self.assertEqual(legacy_row, ("LEGACY-001",))

    def test_invalid_and_duplicate_migration_ids_are_rejected(self):
        working_copy = self.copy_legacy_fixture("working-validation.db")
        noop = lambda connection: None
        with database(working_copy) as connection:
            with self.assertRaises(ValueError):
                apply_migrations(connection, [Migration("Bad ID", "invalid", noop)])
            duplicate = Migration("0003_duplicate", "duplicate", noop)
            with self.assertRaises(ValueError):
                apply_migrations(connection, [duplicate, duplicate])


if __name__ == "__main__":
    unittest.main()
