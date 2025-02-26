import os
import psycopg2
from psycopg2.extras import DictCursor
import sqlite3

def get_db_connection():
    """Get database connection using environment variables"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Production database (Render)
        conn = psycopg2.connect(database_url)
    else:
        # Local development - use SQLite
        print("DATABASE_URL not set. Using local SQLite database for development.")
        conn = sqlite3.connect('mailfoxes.db')
        conn.row_factory = sqlite3.Row
    return conn

def count_emails():
    try:
        # Connect to the database using environment variable
        conn = get_db_connection()
        
        # Check if we're using SQLite or PostgreSQL
        is_sqlite = 'sqlite3.Connection' in str(type(conn))
        
        if is_sqlite:
            cur = conn.cursor()
        else:
            cur = conn.cursor(cursor_factory=DictCursor)
        
        # Execute the count query
        cur.execute("SELECT COUNT(*) FROM emails")
        count = cur.fetchone()[0]
        
        # Close the connection
        cur.close()
        conn.close()
        
        print(f"Total number of emails in the database: {count}")
        return count
    except Exception as e:
        print(f"Error counting emails: {str(e)}")
        return None

if __name__ == "__main__":
    count_emails()
