from flask import Flask, request, jsonify
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import Json
from urllib.parse import urlparse

app = Flask(__name__)

def get_db_connection():
    """Create a database connection"""
    database_url = os.environ.get('DATABASE_URL')
    
    # Heroku-style DATABASE_URL needs to be modified for psycopg2
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return psycopg2.connect(database_url)

def init_db():
    """Initialize the database table"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create emails table if it doesn't exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id SERIAL PRIMARY KEY,
            to_address TEXT NOT NULL,
            from_address TEXT NOT NULL,
            subject TEXT,
            email_text TEXT,
            urls JSONB,
            received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

def extract_urls(text):
    """Extract URLs from text using regex"""
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

@app.route('/')
def home():
    return 'Mailfoxes Email Server is Running!'

@app.route('/parse-email', methods=['POST'])
def parse_email():
    try:
        # Get email text content
        email_text = request.form.get('text', '')
        
        # Extract URLs from the email text
        urls = extract_urls(email_text)
        
        # Store email in database
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO emails (to_address, from_address, subject, email_text, urls)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            request.form.get('to', ''),
            request.form.get('from', ''),
            request.form.get('subject', ''),
            email_text,
            Json(urls)
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"Received email: {request.form.get('subject', '')}")
        print(f"Found URLs: {urls}")
        
        return 'OK', 200
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/emails', methods=['GET'])
def view_emails():
    """View all received emails - for testing"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM emails ORDER BY received_at DESC')
    emails = cur.fetchall()
    
    # Convert to list of dictionaries
    columns = ['id', 'to_address', 'from_address', 'subject', 'email_text', 'urls', 'received_at']
    result = []
    for email in emails:
        result.append(dict(zip(columns, email)))
    
    cur.close()
    conn.close()
    
    return jsonify(result)

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start server
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
