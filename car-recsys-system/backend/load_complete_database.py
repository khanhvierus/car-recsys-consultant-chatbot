#!/usr/bin/env python3
"""
Complete Database Loading Script
Loads all 7 CSV files into PostgreSQL database
"""
import pandas as pd
import psycopg2
from psycopg2 import sql
import sys
import os

# Database configuration
DB_CONFIG = {
    'host': os.getenv('PGHOST', 'postgres'),  # Default to 'postgres' for Docker
    'database': os.getenv('PGDATABASE', 'car_recsys'),
    'user': os.getenv('PGUSER', 'admin'),
    'password': os.getenv('PGPASSWORD', 'admin123')
}

DATASETS_PATH = os.getenv('DATASETS_PATH', "/app/datasets")

def connect_db():
    """Connect to PostgreSQL database"""
    return psycopg2.connect(**DB_CONFIG)

def load_csv(filename):
    """Load CSV file with error handling"""
    filepath = os.path.join(DATASETS_PATH, filename)
    print(f"  📂 Reading {filename}...")
    df = pd.read_csv(filepath, low_memory=False)
    print(f"  ✅ Loaded {len(df):,} rows with {len(df.columns)} columns")
    return df

def create_table_from_dataframe(conn, table_name, df, primary_key=None):
    """Create table dynamically from DataFrame structure"""
    cur = conn.cursor()
    
    # Map pandas dtypes to PostgreSQL types
    type_mapping = {
        'int64': 'BIGINT',
        'float64': 'NUMERIC',
        'bool': 'BOOLEAN',
        'object': 'TEXT',
        'datetime64[ns]': 'TIMESTAMP'
    }
    
    columns = []
    for col, dtype in df.dtypes.items():
        pg_type = type_mapping.get(str(dtype), 'TEXT')
        columns.append(f'"{col}" {pg_type}')
    
    # Add metadata columns
    columns.append('created_at TIMESTAMP DEFAULT NOW()')
    
    # Add primary key if specified
    pk_clause = f', PRIMARY KEY ("{primary_key}")' if primary_key else ''
    
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id SERIAL,
        {', '.join(columns)}
        {pk_clause}
    )
    """
    
    print(f"  🔧 Creating/ensuring table {table_name}...")
    cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    cur.execute(create_sql)
    conn.commit()
    cur.close()

def insert_dataframe(conn, table_name, df, remove_duplicates_by=None):
    """Insert DataFrame into table using COPY
    
    Args:
        remove_duplicates_by: Column name or list of columns to use for deduplication
                             None means keep all rows (no deduplication)
    """
    cur = conn.cursor()
    
    # Remove duplicates only if specified
    original_len = len(df)
    if remove_duplicates_by:
        if isinstance(remove_duplicates_by, str):
            remove_duplicates_by = [remove_duplicates_by]
        df = df.drop_duplicates(subset=remove_duplicates_by, keep='first')
        if len(df) < original_len:
            print(f"  🧹 Removed {original_len - len(df):,} duplicates")
    
    # Prepare temp CSV
    temp_file = f'/tmp/temp_{table_name.replace(".", "_")}.csv'
    df.to_csv(temp_file, index=False, header=False)
    
    # Build COPY command
    columns = [f'"{col}"' for col in df.columns]
    copy_sql = f"""
    COPY {table_name} ({', '.join(columns)})
    FROM STDIN WITH CSV
    """
    
    print(f"  ⬆️  Inserting {len(df):,} rows...")
    with open(temp_file, 'r') as f:
        cur.copy_expert(copy_sql, f)
    
    conn.commit()
    os.remove(temp_file)
    
    # Verify
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cur.fetchone()[0]
    print(f"  ✅ Verified: {count:,} rows in {table_name}")
    
    cur.close()
    return count

def main():
    print("\n" + "="*80)
    print("🚀 COMPLETE DATABASE LOADING SCRIPT")
    print("="*80)
    
    try:
        conn = connect_db()
        conn.autocommit = False
        
        print("\n📊 Loading datasets...\n")
        
        total_rows = 0
        
        # 1. Used Vehicles
        print("1️⃣  USED VEHICLES")
        print("-" * 80)
        df = load_csv('used_vehicles.csv')
        create_table_from_dataframe(conn, 'raw.used_vehicles', df, primary_key='vehicle_id')
        count = insert_dataframe(conn, 'raw.used_vehicles', df, remove_duplicates_by='vehicle_id')
        total_rows += count
        conn.commit()
        print()
        
        # 2. New Vehicles
        print("2️⃣  NEW VEHICLES")
        print("-" * 80)
        df = load_csv('new_vehicles.csv')
        create_table_from_dataframe(conn, 'raw.new_vehicles', df, primary_key='vehicle_id')
        count = insert_dataframe(conn, 'raw.new_vehicles', df, remove_duplicates_by='vehicle_id')
        total_rows += count
        conn.commit()
        print()
        
        # 3. Sellers
        print("3️⃣  SELLERS")
        print("-" * 80)
        df = load_csv('sellers.csv')
        # Remove rows with null seller_key
        df = df[df['seller_key'].notna()]
        create_table_from_dataframe(conn, 'raw.sellers', df, primary_key='seller_key')
        count = insert_dataframe(conn, 'raw.sellers', df, remove_duplicates_by='seller_key')
        total_rows += count
        conn.commit()
        print()
        
        # 4. Reviews & Ratings (NO deduplication - multiple reviews per vehicle)
        print("4️⃣  REVIEWS & RATINGS")
        print("-" * 80)
        df = load_csv('reviews_ratings.csv')
        create_table_from_dataframe(conn, 'raw.reviews_ratings', df)
        count = insert_dataframe(conn, 'raw.reviews_ratings', df, remove_duplicates_by=None)
        total_rows += count
        conn.commit()
        print()
        
        # 5. Vehicle Features (NO deduplication - multiple features per vehicle)
        print("5️⃣  VEHICLE FEATURES")
        print("-" * 80)
        df = load_csv('vehicle_features.csv')
        create_table_from_dataframe(conn, 'raw.vehicle_features', df)
        count = insert_dataframe(conn, 'raw.vehicle_features', df, remove_duplicates_by=None)
        total_rows += count
        conn.commit()
        print()
        
        # 6. Vehicle Images (NO deduplication - multiple images per vehicle)
        print("6️⃣  VEHICLE IMAGES")
        print("-" * 80)
        df = load_csv('vehicle_images.csv')
        create_table_from_dataframe(conn, 'raw.vehicle_images', df)
        count = insert_dataframe(conn, 'raw.vehicle_images', df, remove_duplicates_by=None)
        total_rows += count
        conn.commit()
        print()
        
        # 7. Seller-Vehicle Relationships (Deduplicate by vehicle_id + seller_key)
        print("7️⃣  SELLER-VEHICLE RELATIONSHIPS")
        print("-" * 80)
        df = load_csv('seller_vehicle_relationships.csv')
        create_table_from_dataframe(conn, 'raw.seller_vehicle_relationships', df)
        count = insert_dataframe(conn, 'raw.seller_vehicle_relationships', df, 
                                remove_duplicates_by=['vehicle_id', 'seller_key'])
        total_rows += count
        conn.commit()
        print()
        
        # Final Summary
        print("="*80)
        print("✅ DATABASE LOADING COMPLETED!")
        print("="*80)
        
        cur = conn.cursor()
        tables = [
            'used_vehicles',
            'new_vehicles',
            'sellers',
            'reviews_ratings',
            'vehicle_features',
            'vehicle_images',
            'seller_vehicle_relationships'
        ]
        
        print("\n📊 FINAL SUMMARY:")
        print("-" * 80)
        grand_total = 0
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM raw.{table}")
            count = cur.fetchone()[0]
            grand_total += count
            print(f"  ✅ {table:40s}: {count:>12,} rows")
        
        print("-" * 80)
        print(f"  🎯 TOTAL ROWS LOADED                  : {grand_total:>12,}")
        print("="*80 + "\n")
        
        cur.close()
        conn.close()
        
        print("🎉 All data loaded successfully!")
        print("🔗 PostgREST API: http://localhost:3001")
        print("🔧 Bytebase UI: http://localhost:8080")
        print()
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
            conn.close()
        sys.exit(1)

if __name__ == "__main__":
    main()
