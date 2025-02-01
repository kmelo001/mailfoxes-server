from flask import Flask, request, jsonify
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
from email.parser import Parser

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
    # Debug: Print the entire form posted by SendGrid
    print("==== Incoming SendGrid Form ====")
    print(request.form)

    try:
        # 1) Grab the full raw email from the form data
        raw_email = request.form.get('email', '')

        # 2) Parse the raw MIME into a Python email object
        if not raw_email.strip():
            # If there's nothing in 'email', return early or store an empty message
            print("No raw email data found in request.")
            return 'No raw email data', 400

        parsed_email = Parser().parsestr(raw_email)

        # 3) Extract text/plain and text/html parts
        text_body = ""
        html_body = ""

        # Walk through each MIME part
        for part in parsed_email.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                # Decode the payload in case it's Base64 or quoted-printable
                text_body += part.get_payload(decode=True).decode(errors='replace')
            elif content_type == "text/html":
                html_body += part.get_payload(decode=True).decode(errors='replace')

        # Decide which body to store (plain text if available, otherwise HTML)
        email_body = text_body.strip() if text_body.strip() else html_body.strip()

        # 4) Extract URLs from whichever body we’re using
        urls = extract_urls(email_body)

        # 5) Insert into the database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO emails (to_address, from_address, subject, body_text, urls, received_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            parsed_email["to"],
            parsed_email["from"],
            parsed_email["subject"],
            email_body,
            urls,
            datetime.now()
        ))
        conn.commit()
        cur.close()
        conn.close()

        print(f"Received email: {parsed_email['subject']}")
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
