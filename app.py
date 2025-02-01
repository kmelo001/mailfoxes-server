from flask import Flask, request, jsonify
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)

# Database connection
def get_db_connection():
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    return conn

# Create table if it doesn't exist
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id SERIAL PRIMARY KEY,
            to_address TEXT,
            from_address TEXT,
            subject TEXT,
            body_text TEXT,
            urls TEXT[],
            received_at TIMESTAMP
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def extract_urls(text):
    """Extract URLs from text or HTML using a regex."""
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

@app.route('/')
def home():
    return 'Mailfoxes Email Server is Running!'

@app.route('/parse-email', methods=['POST'])
def parse_email():
    # 1) Print the raw form data from SendGrid (for debugging)
    print("==== Incoming SendGrid Form ====")
    print(request.form)

    try:
        # 2) Capture both plaintext and HTML parts
        text_body = request.form.get('text', '')
        html_body = request.form.get('html', '')

        # Decide which to use as the email body
        if text_body:
            email_body = text_body
        else:
            email_body = html_body

        # Extract URLs from whichever body we have
        urls = extract_urls(email_body)
        
        # Insert into the database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO emails (to_address, from_address, subject, body_text, urls, received_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            request.form.get('to', ''),
            request.form.get('from', ''),
            request.form.get('subject', ''),
            email_body,
            urls,
            datetime.now()
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"Received email: {request.form.get('subject', '')}")
        return 'OK', 200
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/emails', methods=['GET'])
def view_emails():
    """View all received emails"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute('SELECT * FROM emails ORDER BY received_at DESC')
        emails = cur.fetchall()
        cur.close()
        conn.close()
        
        # Convert rows to dictionaries
        emails_list = [dict(email) for email in emails]
        return jsonify(emails_list)
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

# Initialize the database when the app starts
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
