#!/usr/bin/env python3
import sqlite3
import psycopg2
from psycopg2.extras import DictCursor
import os
import sys
import re
from datetime import datetime

def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Production database (Render)
        conn = psycopg2.connect(database_url)
    else:
        # Local development - use SQLite
        print("DATABASE_URL not set. Using local SQLite database for development.")
        conn = sqlite3.connect('mailfoxes.db')
    return conn

def get_spam_score(email_content):
    """Get spam score using the spamcheck library."""
    try:
        import spamcheck
        
        # We only need the score, not the full report
        result = spamcheck.check(email_content, report=False)
        return result['score']
    except ImportError:
        print("spamcheck library not installed. Install with: pip install spamcheck")
        return 0
    except Exception as e:
        print(f"Error checking spam score: {str(e)}")
        return 0  # Default score if API call fails

def backfill_spam_scores_for_inbox(source_id, limit=10):
    """Calculate and update spam scores for emails in a specific inbox."""
    conn = get_db_connection()
    
    # Check if we're using SQLite
    is_sqlite = 'sqlite3.Connection' in str(type(conn))
    
    if is_sqlite:
        # SQLite uses ? as placeholder
        placeholder = "?"
        conn.row_factory = lambda cursor, row: {
            col[0]: row[idx] for idx, col in enumerate(cursor.description)
        }
        cur = conn.cursor()
    else:
        # PostgreSQL uses %s as placeholder
        placeholder = "%s"
        cur = conn.cursor(cursor_factory=DictCursor)
    
    # Get the source name for logging
    query = f"SELECT display_name FROM email_sources WHERE id = {placeholder}"
    cur.execute(query, (source_id,))
    source = cur.fetchone()
    source_name = source['display_name'] if source else f"Source ID {source_id}"
    
    print(f"Processing up to {limit} emails for {source_name}...")
    
    # Get emails without spam scores (or with score = 0)
    query = f"""
        SELECT id, from_address, to_address, subject, body_text
        FROM emails
        WHERE source_id = {placeholder} AND (spam_score IS NULL OR spam_score = 0)
        ORDER BY received_at DESC
        LIMIT {placeholder}
    """
    cur.execute(query, (source_id, limit))
    
    emails = cur.fetchall()
    print(f"Found {len(emails)} emails to process")
    
    for email in emails:
        # Reconstruct raw email format for spam checking
        raw_email = f"From: {email['from_address']}\nTo: {email['to_address']}\nSubject: {email['subject']}\n\n{email['body_text']}"
        
        # Calculate spam score
        spam_score = get_spam_score(raw_email)
        
        # Update the database
        query = f"""
            UPDATE emails
            SET spam_score = {placeholder}
            WHERE id = {placeholder}
        """
        cur.execute(query, (spam_score, email['id']))
        
        print(f"Email ID {email['id']} - Score: {spam_score}")
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"Completed processing for {source_name}")

def backfill_all_inboxes(limit_per_inbox=10):
    """Calculate and update spam scores for all inboxes."""
    conn = get_db_connection()
    
    # Check if we're using SQLite
    is_sqlite = 'sqlite3.Connection' in str(type(conn))
    
    if is_sqlite:
        # SQLite setup
        conn.row_factory = lambda cursor, row: {
            col[0]: row[idx] for idx, col in enumerate(cursor.description)
        }
        cur = conn.cursor()
    else:
        # PostgreSQL setup
        cur = conn.cursor(cursor_factory=DictCursor)
    
    # Get all sources
    cur.execute("SELECT id, display_name FROM email_sources ORDER BY id")
    sources = cur.fetchall()
    
    cur.close()
    conn.close()
    
    for source in sources:
        try:
            backfill_spam_scores_for_inbox(source['id'], limit_per_inbox)
        except Exception as e:
            print(f"Error processing source {source['display_name']} (ID {source['id']}): {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        # Process all inboxes if --all flag is provided
        backfill_all_inboxes(10)
    else:
        # Process just Agora - MoneyMorning - Free (ID 14) by default
        backfill_spam_scores_for_inbox(14, 10)
        print("\nTo process all inboxes, run: python3 backfill_spam_scores_standalone.py --all")
