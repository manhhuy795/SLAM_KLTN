import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from init_db import migrate_nullable_task_fields


class TaskNullableMigrationTests(unittest.TestCase):
    def test_preserves_rows_constraints_indexes_and_foreign_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wrms.db"
            with closing(sqlite3.connect(path)) as db:
                db.execute("PRAGMA foreign_keys=ON")
                db.executescript("""
                    CREATE TABLE products (id INTEGER PRIMARY KEY);
                    CREATE TABLE locations (id INTEGER PRIMARY KEY);
                    CREATE TABLE tasks (
                        id INTEGER PRIMARY KEY,
                        product_id INTEGER NOT NULL,
                        dropoff_location_id INTEGER NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('WAITING', 'COMPLETED')),
                        FOREIGN KEY(product_id) REFERENCES products(id),
                        FOREIGN KEY(dropoff_location_id) REFERENCES locations(id));
                    CREATE INDEX ix_tasks_product_id ON tasks(product_id);
                    CREATE TABLE task_proofs (id INTEGER PRIMARY KEY,
                        task_id INTEGER REFERENCES tasks(id));
                    INSERT INTO products VALUES (1);
                    INSERT INTO locations VALUES (1);
                    INSERT INTO tasks VALUES (1, 1, 1, 'WAITING');
                    INSERT INTO task_proofs VALUES (1, 1);
                """)
            backup = migrate_nullable_task_fields(path)
            self.assertTrue(backup.exists())
            with closing(sqlite3.connect(path)) as db:
                db.execute("PRAGMA foreign_keys=ON")
                self.assertEqual(db.execute("SELECT * FROM tasks WHERE id=1").fetchone(),
                                 (1, 1, 1, "WAITING"))
                db.execute("INSERT INTO tasks VALUES (2, NULL, NULL, 'WAITING')")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='ix_tasks_product_id'").fetchone())
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("INSERT INTO tasks VALUES (3, NULL, NULL, 'INVALID')")
            self.assertIsNone(migrate_nullable_task_fields(path))


if __name__ == "__main__":
    unittest.main()
