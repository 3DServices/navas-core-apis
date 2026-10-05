# database/manual

SQL in this folder is **never run automatically**.

`scripts/run_migrations.py` reads `database/migrations/` and executes every file
matching `^(\d+)_.+\.sql$` in order. Anything here is deliberately outside that
directory and carries no numeric prefix, so it cannot be picked up by accident.

These scripts change privileges, roles or other things that want a human to read
them first, choose a password, and run them knowingly against a named database.

| file | what it does | run it when |
|---|---|---|
| `waswa_readonly_role.sql` | creates the `navas_waswa` least-privilege role | before ticket A1c, and verify with `scripts/waswa_grant_check.py` first |
