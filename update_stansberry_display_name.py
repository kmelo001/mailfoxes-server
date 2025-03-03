#!/usr/bin/env python3
"""
Script to update the display name of "Exct- Auto" to "Stansberry Research - Free"
This script is designed to be run on the server where the app is deployed.
"""
import os
import psycopg2
from psycopg2.extras import DictCursor

def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # For local development, use a default PostgreSQL connection string
        print("DATABASE_URL not set. Using default PostgreSQL connection string.")
        database_url = "postgresql://postgres:postgres@localhost:5432/mailfoxes"
    
    # Always use PostgreSQL
    conn = psycopg2.connect(database_url)
    return conn

def update_display_name():
    try:
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Look for any sources that might match "Exct- Auto" with different case variations
        # or sources that have "exct" in their name or email address
        print("Searching for email sources that might be Stansberry Research...")
        cur.execute("""
            SELECT id, name, email_address, display_name 
            FROM email_sources 
            WHERE 
                display_name ILIKE 'Exct%Auto' OR
                name ILIKE 'exct%' OR
                email_address ILIKE '%exct%' OR
                email_address ILIKE '%stansberry%'
        """)
        sources = cur.fetchall()
        print(f"Found {len(sources)} potential matching sources")
        
        if not sources:
            print("No potential matching email sources found")
            cur.close()
            conn.close()
            return
        
        # Print all potential matches for review
        print("\nPotential matches:")
        for i, source in enumerate(sources):
            print(f"{i+1}. ID: {source['id']}, Name: {source['name']}, Email: {source['email_address']}, Display Name: {source['display_name']}")
        
        # Update all matches to the new display name
        print("\nUpdating all potential matches to 'Stansberry Research - Free'...")
        for source in sources:
            source_id = source['id']
            old_display_name = source['display_name']
            
            print(f"Updating source ID {source_id} from '{old_display_name}' to 'Stansberry Research - Free'")
            
            cur.execute(
                "UPDATE email_sources SET display_name = %s WHERE id = %s",
                ("Stansberry Research - Free", source_id)
            )
        
        # Commit the changes
        conn.commit()
        print(f"Updated {len(sources)} email source(s) successfully")
        
        # Close the connection
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    update_display_name()
    print("Display name update complete")
