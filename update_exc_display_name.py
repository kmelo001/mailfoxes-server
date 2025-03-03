#!/usr/bin/env python3
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
        
        print("Searching for email sources with display name 'Exc - Auto'...")
        # Find the email source with display name "Exc - Auto"
        cur.execute("SELECT id, name, email_address FROM email_sources WHERE display_name = 'Exc - Auto'")
        sources = cur.fetchall()
        print(f"Found {len(sources)} matching sources")
        
        if not sources:
            print("No email sources found with display name 'Exc - Auto'")
            cur.close()
            conn.close()
            return
        
        # Update the display name for each matching source
        for source in sources:
            source_id = source['id']
            name = source['name']
            email = source['email_address']
            
            print(f"Updating source ID {source_id} ({name}, {email}) from 'Exc - Auto' to 'Stansberry Research - Free'")
            
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
