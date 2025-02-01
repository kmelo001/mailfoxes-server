from flask import Flask, request, jsonify, render_template
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
from email.parser import Parser
from urllib.parse import urlparse

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
    url_pattern = r'http[s]?://(?:[a-zA-Z0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
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
                text_body += part.get_payload(decode=True).decode(errors='replace')
            elif content_type == "text/html":
                html_body += part.get_payload(decode=True).decode(errors='replace')

        # Choose plain text if available; otherwise, use HTML
        email_body = text_body.strip() if text_body.strip() else html_body.strip()

        # 4) Extract URLs from the chosen body
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
    """View all received emails as JSON."""
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

@app.route('/emails/view', methods=['GET'])
def view_emails_html():
    """Render a user-friendly HTML page displaying the received emails."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Add sorting parameters
        sort = request.args.get('sort', 'newest')
        limit = request.args.get('limit', '10')
        
        # Base query with dynamic sorting
        if sort == 'oldest':
            order_by = 'ASC'
        else:
            order_by = 'DESC'
            
        cur.execute(f'SELECT * FROM emails ORDER BY received_at {order_by} LIMIT %s', (limit,))
        emails = cur.fetchall()
        cur.close()
        conn.close()

        # Convert rows to list of dicts and add computed fields
        emails_list = []
        for email in emails:
            email_dict = dict(email)
            
            # Ensure received_at is a datetime object
            if isinstance(email_dict['received_at'], str):
                email_dict['received_at'] = datetime.strptime(email_dict['received_at'], '%Y-%m-%d %H:%M:%S.%f')
            
            # Add computed fields
            email_dict['subject_length'] = len(email_dict['subject']) if email_dict['subject'] else 0
            email_dict['word_count'] = len(email_dict['body_text'].split()) if email_dict['body_text'] else 0
            email_dict['link_count'] = len(email_dict['urls']) if email_dict['urls'] else 0
            
            # Generate a share URL
            email_dict['share_url'] = request.url_root + f"emails/view?id={email_dict['id']}"
            
            emails_list.append(email_dict)

        return render_template('emails.html', 
                             emails=emails_list,
                             current_sort=sort,
                             current_limit=limit)

    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/emails/view/<int:email_id>', methods=['GET'])
def view_single_email(email_id):
    """Render a single email view."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute('SELECT * FROM emails WHERE id = %s', (email_id,))
        email = cur.fetchone()
        cur.close()
        conn.close()

        if email is None:
            return "Email not found", 404

        email_dict = dict(email)
        if isinstance(email_dict['received_at'], str):
            email_dict['received_at'] = datetime.strptime(email_dict['received_at'], '%Y-%m-%d %H:%M:%S.%f')

        return render_template('email_single.html', email=email_dict)

    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

# Initialize the database when the app starts
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
