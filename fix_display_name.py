#!/usr/bin/env python3
"""
Script to fix the display name of "Exct - Auto" to "Stansberry Research - Free"
This script uses a flexible pattern match and includes verification steps.
"""
import os
import psycopg2
from psycopg2.extras import DictCursor

# Get database URL from environment variable
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    print("ERROR: DATABASE_URL environment variable not set.")
    print("This script is designed to be run on the server where the app is deployed.")
    print("Please set the DATABASE_URL environment variable and try again.")
    exit(1)

try:
    # Connect to the database
    print("Connecting to database...")
    conn = psycopg2.connect(database_url)
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # First, find and print all entries that might match to verify what we're working with
    print("\n=== BEFORE UPDATE ===")
    print("Searching for all possible matches...")
    cur.execute("""
        SELECT id, name, email_address, display_name 
        FROM email_sources 
        WHERE display_name LIKE 'Exct%Auto' OR display_name = 'Exct - Auto'
    """)
    sources = cur.fetchall()
    
    if not sources:
        print("No matching sources found with display name like 'Exct%Auto'")
        
        # Try a broader search
        print("\nTrying a broader search...")
        cur.execute("""
            SELECT id, name, email_address, display_name 
            FROM email_sources 
            WHERE display_name LIKE '%Exct%' OR display_name LIKE '%Auto%'
        """)
        sources = cur.fetchall()
        
        if not sources:
            print("Still no matches found. Let's look at all display names:")
            cur.execute("SELECT id, display_name FROM email_sources ORDER BY id")
            all_sources = cur.fetchall()
            print("\nAll display names in the database:")
            for source in all_sources:
                print(f"ID: {source['id']}, Display Name: {source['display_name']}")
            
            print("\nNo automatic update performed. Please check the display names above and update manually.")
            cur.close()
            conn.close()
            exit(1)
    
    # Print all potential matches
    print(f"\nFound {len(sources)} potential matches:")
    for source in sources:
        print(f"ID: {source['id']}, Name: {source['name']}, Email: {source['email_address']}, Display Name: '{source['display_name']}'")
    
    # Update all matches
    print("\n=== UPDATING ===")
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
    
    # Verify the update
    print("\n=== AFTER UPDATE ===")
    print("Verifying update...")
    cur.execute("""
        SELECT id, name, email_address, display_name 
        FROM email_sources 
        WHERE id IN %s
    """, (tuple([s['id'] for s in sources]),))
    
    updated_sources = cur.fetchall()
    for source in updated_sources:
        print(f"ID: {source['id']}, Display Name: '{source['display_name']}'")
    
    # Close the connection
    cur.close()
    conn.close()
    
    print("\n=== SUMMARY ===")
    print(f"Updated {len(sources)} source(s) to display name 'Stansberry Research - Free'")
    print("\nPlease verify the changes by visiting:")
    print("1. https://mailfoxes-server.onrender.com/inbox")
    print("2. https://mailfoxes-server.onrender.com/emails/view")
    print("\nIf the display name is still not updated, you may need to clear your browser cache or wait a few minutes for the changes to propagate.")
    
except Exception as e:
    print(f"Error: {str(e)}")
