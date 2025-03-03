#!/usr/bin/env python3
"""
Script to update the display name of "Exct- Auto" to "Stansberry Research - Free"
This script is designed to be run on the server where the app is deployed.
"""
import os
import sys
from app import get_db_connection

def update_display_name():
    try:
        print("Connecting to database using app's connection method...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("Searching for email sources with display name 'Exct- Auto'...")
        # Find the email source with display name "Exct- Auto"
        cur.execute("SELECT id, name, email_address FROM email_sources WHERE display_name = 'Exct- Auto'")
        sources = cur.fetchall()
        print(f"Found {len(sources)} matching sources")
        
        if not sources:
            print("No email sources found with display name 'Exct- Auto'")
            cur.close()
            conn.close()
            return
        
        # Update the display name for each matching source
        for source in sources:
            source_id = source[0]  # id is the first column
            name = source[1]       # name is the second column
            email = source[2]      # email_address is the third column
            
            print(f"Updating source ID {source_id} ({name}, {email}) from 'Exct- Auto' to 'Stansberry Research - Free'")
            
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
