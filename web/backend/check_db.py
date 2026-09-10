from sqlalchemy import inspect

from app.db.database import engine


inspector = inspect(engine)
tables = inspector.get_table_names()

print("\n===== WRMS DATABASE CHECK =====")
print(f"\nTổng số bảng: {len(tables)}")


for table in tables:
    print("\n" + "=" * 70)
    print(f"TABLE: {table.upper()}")
    print("=" * 70)

    print("\n[COLUMNS]")
    for column in inspector.get_columns(table):
        print(
            f"  {column['name']:<24}"
            f"{str(column['type']):<20}"
            f"nullable={column['nullable']}"
        )

    print("\n[FOREIGN KEYS]")
    foreign_keys = inspector.get_foreign_keys(table)

    if not foreign_keys:
        print("  None")
    else:
        for fk in foreign_keys:
            print(
                f"  {fk['constrained_columns']}"
                f" -> {fk['referred_table']}"
                f".{fk['referred_columns']}"
            )

    print("\n[UNIQUE CONSTRAINTS]")
    uniques = inspector.get_unique_constraints(table)

    if not uniques:
        print("  None")
    else:
        for unique in uniques:
            print(
                f"  {unique['name']}: "
                f"{unique['column_names']}"
            )

    print("\n[CHECK CONSTRAINTS]")
    checks = inspector.get_check_constraints(table)

    if not checks:
        print("  None")
    else:
        for check in checks:
            print(
                f"  {check['name']}: "
                f"{check['sqltext']}"
            )

    print("\n[INDEXES]")
    indexes = inspector.get_indexes(table)

    if not indexes:
        print("  None")
    else:
        for index in indexes:
            print(
                f"  {index['name']}: "
                f"{index['column_names']}"
            )


print("\n===== CHECK COMPLETED =====")