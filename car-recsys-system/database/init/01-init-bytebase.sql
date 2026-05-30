-- Create Bytebase admin user with full permissions
CREATE USER bytebase WITH PASSWORD 'bytebase123' SUPERUSER CREATEDB CREATEROLE LOGIN;

-- Grant all privileges on database
GRANT ALL PRIVILEGES ON DATABASE car_recsys TO bytebase;

-- Connect to car_recsys database
\c car_recsys

-- Create the medallion schemas up front so the grants below resolve.
-- (02-create-schema.sql also CREATE SCHEMA IF NOT EXISTS — harmless overlap.)
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Grant usage and create on schemas
GRANT USAGE, CREATE ON SCHEMA bronze TO bytebase;
GRANT USAGE, CREATE ON SCHEMA silver TO bytebase;
GRANT USAGE, CREATE ON SCHEMA gold TO bytebase;
GRANT USAGE, CREATE ON SCHEMA public TO bytebase;

-- Grant all privileges on all tables in schemas
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bronze TO bytebase;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA silver TO bytebase;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gold TO bytebase;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO bytebase;

-- Grant all privileges on all sequences in schemas
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA bronze TO bytebase;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA silver TO bytebase;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA gold TO bytebase;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO bytebase;

-- Set default privileges for future objects (dbt creates silver/gold objects later)
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT ALL ON TABLES TO bytebase;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver GRANT ALL ON TABLES TO bytebase;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT ALL ON TABLES TO bytebase;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO bytebase;

ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT ALL ON SEQUENCES TO bytebase;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver GRANT ALL ON SEQUENCES TO bytebase;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT ALL ON SEQUENCES TO bytebase;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO bytebase;

-- Create admin user for general use (optional)
CREATE USER admin_user WITH PASSWORD 'admin_pass123';
GRANT ALL PRIVILEGES ON DATABASE car_recsys TO admin_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bronze, silver, gold, public TO admin_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA bronze, silver, gold, public TO admin_user;
ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO admin_user;
ALTER DEFAULT PRIVILEGES GRANT ALL ON SEQUENCES TO admin_user;
