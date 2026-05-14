# Database Migrations

This folder contains SQL migration scripts for the Navas IoT Backend API project.

## How to Run Migrations

### Using Beekeeper Studio:
1. Open Beekeeper Studio
2. Connect to your PostgreSQL database using the credentials in `app.py`
3. Open the migration file from `migrations/` folder
4. Execute the SQL script
5. Verify the tables were created successfully

### Using psql (Command Line):
```bash
psql -h 165.232.128.208 -U flareconnect -d narva_dbl -p 5432 -f database/migrations/001_create_veba_tables.sql
```

## Migration Files

- `001_create_veba_tables.sql` - Creates VEBA (Vehicle Equipment Booking & Assignment) tables and seed data

## Best Practices

- Always prefix migration files with a number (001, 002, etc.) to maintain order
- Include descriptive comments at the top of each migration
- Use `IF NOT EXISTS` clauses to make migrations idempotent
- Test migrations on a development database first
- Never modify existing migration files after they've been run in production
