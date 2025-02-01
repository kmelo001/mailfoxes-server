from flask import Flask, request, jsonify, render_template, Response, redirect
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
from email.parser import Parser
from email.policy import default
from email.utils import parseaddr
from email.header import decode_header
import base64
import quopri
from urllib.parse import urlparse
import json

app = Flask(__name__)

def decode_email_subject(subject):
    """Decode email subject that might be encoded."""
    if not subject:
        return ""
    decoded_parts = []
    for part, charset in decode_header(subject):
        if isinstance(part, bytes):
            try:
                if charset:
                    decoded_parts.append(part.decode(charset))
                else:
                    decoded_parts.append(part.decode())
            except:
                decoded_parts.append(part.decode('utf-8', 'ignore'))
        else:
            decoded_parts.append(part)
    return ' '.join(decoded_parts)

def decode_email_body(part):
    """Decode email body parts properly."""
    content = part.get_payload(decode=True)
    charset = part.get_content_charset()
    
    if charset:
        try:
            return content.decode(charset)
        except:
            return content.decode('utf-8', 'ignore')
    
    try:
        return content.decode()
    except:
        return content.decode('utf-8', 'ignore')

def get_db_connection():
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # First create the table if it doesn't exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id SERIAL PRIMARY KEY,
            to_address TEXT,
            from_address TEXT,
            subject TEXT,
            body_text TEXT,
            urls TEXT[],
            received_at TIMESTAMP,
            raw_email TEXT
        );
    ''')
    
    # Check if raw_email column exists
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='emails' AND column_name='raw_email';
    """)
    
    # Add raw_email column if it doesn't exist
    if cur.fetchone() is None:
        try:
            cur.execute('ALTER TABLE emails ADD COLUMN raw_email TEXT;')
            print("Added raw_email column to emails table")
        except Exception as e:
            print(f"Error adding raw_email column: {e}")
    
    conn.commit()
    cur.close()
    conn.close()

def extract_urls(text):
    """Extract URLs from text or HTML using a regex."""
    url_pattern = r'http[s]?://(?:[a-zA-Z0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

def process_email_data(email_dict):
    """Process email data to add computed fields."""
    if isinstance(email_dict['received_at'], str):
        email_dict['received_at'] = datetime.strptime(email_dict['received_at'], '%Y-%m-%d %H:%M:%S.%f')
    
    # Add computed fields
    email_dict['subject_length'] = len(email_dict['subject']) if email_dict['subject'] else 0
    email_dict['word_count'] = len(email_dict['body_text'].split()) if email_dict['body_text'] else 0
    email_dict['link_count'] = len(email_dict['urls']) if email_dict['urls'] else 0
    email_dict['share_url'] = f"/emails/view/{email_dict['id']}"
    
    return email_dict

@app.route('/')
def home():
    return redirect('/emails/view')

@app.route('/parse-email', methods=['POST'])
def parse_email():
    print("==== Incoming SendGrid Form ====")
    print(request.form)

    try:
        # Get raw email
        raw_email = request.form.get('email', '')
        if not raw_email.strip():
            print("No raw email data found in request.")
            return 'No raw email data', 400

        # Parse with policy=default for better MIME handling
        parsed_email = Parser(policy=default).parsestr(raw_email)

        # Extract and decode subject
        subject = decode_email_subject(parsed_email['subject'])

        # Extract addresses
        to_addr = parseaddr(parsed_email['to'])[1]
        from_addr = parseaddr(parsed_email['from'])[1]

        # Extract body
        text_body = []
        html_body = []

        def extract_body(message):
            if message.is_multipart():
                for part in message.walk():
                    if part.is_multipart():
                        continue
                    if part.get_content_maintype() == 'text':
                        if part.get_content_subtype() == 'plain':
                            text_body.append(decode_email_body(part))
                        elif part.get_content_subtype() == 'html':
                            html_body.append(decode_email_body(part))
            else:
                content_type = message.get_content_type()
                if content_type == 'text/plain':
                    text_body.append(decode_email_body(message))
                elif content_type == 'text/html':
                    html_body.append(decode_email_body(message))

        extract_body(parsed_email)
        
        # Choose plain text if available; otherwise, use HTML
        email_body = '\n'.join(text_body) if text_body else '\n'.join(html_body)
        
        # Extract URLs
        urls = extract_urls(email_body)

        # Insert into database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO emails (
                to_address, from_address, subject, body_text, urls, received_at, raw_email
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            to_addr,
            from_addr,
            subject,
            email_body,
            urls,
            datetime.now(),
            raw_email  # Store the raw email
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        print(f"Received email: {subject}")
        return jsonify({"status": "success", "id": new_id}), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

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

        emails_list = [process_email_data(dict(email)) for email in emails]
        return jsonify(emails_list)

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/emails/view')
def view_emails_html():
    """Render the main email dashboard."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        sort = request.args.get('sort', 'newest')
        limit = request.args.get('limit', '10')
        time_filter = request.args.get('time', 'all')
        
        query = 'SELECT * FROM emails'
        params = []
        
        if time_filter == 'week':
            query += ' WHERE received_at >= NOW() - INTERVAL \'7 days\''
        elif time_filter == 'month':
            query += ' WHERE received_at >= NOW() - INTERVAL \'30 days\''
        
        query += ' ORDER BY received_at ' + ('DESC' if sort == 'newest' else 'ASC')
        query += ' LIMIT %s'
        params.append(int(limit))
        
        cur.execute(query, params)
        emails = cur.fetchall()
        cur.close()
        conn.close()

        emails_list = [process_email_data(dict(email)) for email in emails]

        return render_template('emails.html', 
                             emails=emails_list,
                             current_sort=sort,
                             current_limit=limit,
                             current_time=time_filter)

    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/emails/view/<int:email_id>')
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

        email_dict = process_email_data(dict(email))
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render_template('email_single.html', email=email_dict)
        else:
            return render_template('emails.html', emails=[email_dict])

    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
