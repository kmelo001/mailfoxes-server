#!/usr/bin/env python3
"""
Script to update the display name of "Exc - Auto" to "Stansberry Research - Free"
This script is designed to be run on the server where the app is deployed.
"""
import os
import psycopg2

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
    cur = conn.cursor()
    
    # Find email sources with "Exc" in the display name
    print("Searching for email sources with 'Exc' in the display name...")
    cur.execute("SELECT id, name, email_address, display_name FROM email_sources WHERE display_name LIKE '%Exc%'")
    sources = cur.fetchall()
    
    if not sources:
        print("No email sources found with 'Exc' in the display name.")
        cur.close()
        conn.close()
        exit(0)
    
    print(f"Found {len(sources)} matching sources:")
    for source in sources:
        source_id, name, email, display_name = source
        print(f"ID: {source_id}, Name: {name}, Email: {email}, Display Name: {display_name}")
    
    # Update the display name for each matching source
    print("\nUpdating display names to 'Stansberry Research - Free'...")
    for source in sources:
        source_id = source[0]
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
