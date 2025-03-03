#!/usr/bin/env python3
"""
Script to directly update the display name of "Exct- Auto" to "Stansberry Research - Free"
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
    
    # Execute the SQL command to update the display name
    print("Executing SQL command to update display name...")
    cur.execute("""
        UPDATE email_sources 
        SET display_name = 'Stansberry Research - Free' 
        WHERE display_name = 'Exct- Auto'
    """)
    
    # Get the number of rows affected
    rows_affected = cur.rowcount
    print(f"Updated {rows_affected} row(s)")
    
    # If no rows were affected, try a pattern match
    if rows_affected == 0:
        print("No exact matches found. Trying pattern match...")
        cur.execute("""
            UPDATE email_sources 
            SET display_name = 'Stansberry Research - Free' 
            WHERE display_name LIKE '%Exct%Auto%'
        """)
        rows_affected = cur.rowcount
        print(f"Updated {rows_affected} row(s) with pattern match")
    
    # Commit the changes
    conn.commit()
    print("Changes committed to database")
    
    # Close the connection
    cur.close()
    conn.close()
    print("Database connection closed")
    
    if rows_affected > 0:
        print("\nSUCCESS: Display name updated successfully!")
        print("Please verify the changes by visiting:")
        print("1. https://mailfoxes-server.onrender.com/inbox")
        print("2. https://mailfoxes-server.onrender.com/emails/view")
    else:
        print("\nWARNING: No rows were updated. Please check if the display name 'Exct- Auto' exists in the database.")
        print("You may need to check the exact display name in the database and update the script accordingly.")
    
except Exception as e:
    print(f"Error: {str(e)}")
