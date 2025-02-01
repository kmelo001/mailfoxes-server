from flask import Flask, request, jsonify, render_template, Response, redirect
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
import json

app = Flask(__name__)

def get_db_connection():
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create table with HTML content column
    cur.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id SERIAL PRIMARY KEY,
            to_address TEXT,
            from_address TEXT,
            subject TEXT,
            body_text TEXT,
            body_html TEXT,
            urls TEXT[],
            received_at TIMESTAMP
        );
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

def extract_urls(text):
    """Extract URLs from text or HTML using a regex."""
    if not text:
        return []
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
    print("==== Incoming SendGrid Parsed Email ====")
    print(request.form)

    try:
        # Get parsed email fields from SendGrid
        to_addr = request.form.get('to', '')
        from_addr = request.form.get('from', '')
        subject = request.form.get('subject', '')
        text_body = request.form.get('text', '')
        html_body = request.form.get('html', '')
        
        # Extract URLs (can get from either text or HTML)
        urls = extract_urls(text_body) if text_body else extract_urls(html_body)

        # Insert into database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO emails (
                to_address, from_address, subject, body_text, body_html, urls, received_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            to_addr,
            from_addr,
            subject,
            text_body,
            html_body,
            urls,
            datetime.now()
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
