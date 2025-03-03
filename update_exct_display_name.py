#!/usr/bin/env python3
"""
Script to update the display name of "Exct - Auto" to "Stansberry Research - Free"
This script shows the exact values before and after the update for verification.
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
        print("\n=== CONNECTING TO DATABASE ===")
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        print("\n=== SHOWING ALL EMAIL SOURCES ===")
        print("This will help us identify the exact record to update")
        cur.execute("""
            SELECT id, name, email_address, display_name 
            FROM email_sources 
            ORDER BY id
        """)
        all_sources = cur.fetchall()
        
        print("\nAll email sources in the database:")
        print("-" * 80)
        print(f"{'ID':<5} {'Display Name':<30} {'Name':<20} {'Email Address':<30}")
        print("-" * 80)
        for source in all_sources:
            print(f"{source['id']:<5} {source['display_name'] or 'None':<30} {source['name']:<20} {source['email_address']:<30}")
        
        print("\n=== FINDING EXACT MATCH FOR 'Exct - Auto' ===")
        cur.execute("""
            SELECT id, name, email_address, display_name 
            FROM email_sources 
            WHERE display_name = 'Exct - Auto'
        """)
        exact_match = cur.fetchall()
        
        if exact_match:
            print(f"Found {len(exact_match)} exact match(es) for 'Exct - Auto':")
            for source in exact_match:
                print(f"ID: {source['id']}, Name: {source['name']}, Email: {source['email_address']}, Display Name: '{source['display_name']}'")
            
            # Update all exact matches
            print("\n=== UPDATING RECORDS ===")
            for source in exact_match:
                source_id = source['id']
                old_display_name = source['display_name']
                
                print(f"Updating source ID {source_id} from '{old_display_name}' to 'Stansberry Research - Free'")
                
                cur.execute(
                    "UPDATE email_sources SET display_name = %s WHERE id = %s",
                    ("Stansberry Research - Free", source_id)
                )
            
            # Commit the changes
            conn.commit()
            print("Changes committed to database")
            
            # Verify the update
            print("\n=== VERIFYING UPDATE ===")
            for source in exact_match:
                source_id = source['id']
                cur.execute("SELECT display_name FROM email_sources WHERE id = %s", (source_id,))
                updated = cur.fetchone()
                print(f"Source ID {source_id} display name is now: '{updated['display_name']}'")
        else:
            print("No exact match found for 'Exct - Auto'")
            
            # Try a broader search
            print("\n=== TRYING BROADER SEARCH ===")
            cur.execute("""
                SELECT id, name, email_address, display_name 
                FROM email_sources 
                WHERE display_name LIKE '%Exct%' OR display_name LIKE '%Auto%'
            """)
            broader_matches = cur.fetchall()
            
            if broader_matches:
                print(f"Found {len(broader_matches)} potential matches:")
                for source in broader_matches:
                    print(f"ID: {source['id']}, Name: {source['name']}, Email: {source['email_address']}, Display Name: '{source['display_name']}'")
                
                # Ask for confirmation before updating
                print("\nBased on the screenshot, we need to update the record with display name 'Exct - Auto'")
                print("Please run this script again with the exact ID to update, using:")
                print("python update_exct_display_name.py <id>")
                print("\nFor example, if the ID is 123, run:")
                print("python update_exct_display_name.py 123")
            else:
                print("No matches found with 'Exct' or 'Auto' in the display name")
                print("Please check the database manually to find the correct record")
        
        # Close the connection
        cur.close()
        conn.close()
        print("\nDatabase connection closed")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        try:
            source_id = int(sys.argv[1])
            
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=DictCursor)
            
            # Get the current display name
            cur.execute("SELECT display_name FROM email_sources WHERE id = %s", (source_id,))
            source = cur.fetchone()
            
            if source:
                old_display_name = source['display_name']
                print(f"\nUpdating source ID {source_id} from '{old_display_name}' to 'Stansberry Research - Free'")
                
                # Update the display name
                cur.execute(
                    "UPDATE email_sources SET display_name = %s WHERE id = %s",
                    ("Stansberry Research - Free", source_id)
                )
                
                # Commit the changes
                conn.commit()
                print("Changes committed to database")
                
                # Verify the update
                cur.execute("SELECT display_name FROM email_sources WHERE id = %s", (source_id,))
                updated = cur.fetchone()
                print(f"Source ID {source_id} display name is now: '{updated['display_name']}'")
            else:
                print(f"No source found with ID {source_id}")
            
            cur.close()
            conn.close()
            
        except ValueError:
            print(f"Invalid ID: {sys.argv[1]}. Please provide a valid numeric ID.")
    else:
        update_display_name()
