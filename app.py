from flask import Flask, request, jsonify, render_template, Response, redirect
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
import json
from functools import wraps

app = Flask(__name__)

# Add API authentication token
API_TOKEN = os.environ.get('API_TOKEN')

def get_db_connection():
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    return conn

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or token != f"Bearer {API_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # First create email_sources table if it doesn't exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS email_sources (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email_address TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # Check if emails table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'emails'
        );
    """)
    table_exists = cur.fetchone()[0]
    
    if not table_exists:
        # Create new emails table with source_id
        cur.execute('''
            CREATE TABLE emails (
                id SERIAL PRIMARY KEY,
                source_id INTEGER REFERENCES email_sources(id),
                to_address TEXT,
                from_address TEXT,
                subject TEXT,
                body_text TEXT,
                body_html TEXT,
                urls TEXT[],
                received_at TIMESTAMP,
                processed BOOLEAN DEFAULT FALSE
            );
        ''')
    else:
        # Add processed column if it doesn't exist
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'emails' AND column_name = 'processed'
            );
        """)
        column_exists = cur.fetchone()[0]
        
        if not column_exists:
            cur.execute('ALTER TABLE emails ADD COLUMN processed BOOLEAN DEFAULT FALSE;')
    
    # Create indexes
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_sources_email 
        ON email_sources(email_address);
    ''')
    
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_emails_source_date 
        ON emails(source_id, received_at DESC);
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

@app.route('/sources/add', methods=['POST'])
def add_source():
    """Add a new email source."""
    try:
        name = request.form.get('name')
        email = request.form.get('email')
        description = request.form.get('description')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO email_sources (name, email_address, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (email_address) DO UPDATE 
            SET name = EXCLUDED.name,
                description = EXCLUDED.description
            RETURNING id
        ''', (name, email, description))
        
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(f'/emails/view?source={new_id}')
        
    except Exception as e:
        return str(e), 500

@app.route('/sources/delete/<int:source_id>', methods=['POST'])
def delete_source(source_id):
    """Delete an email source."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # First update emails to remove the source_id
        cur.execute('UPDATE emails SET source_id = NULL WHERE source_id = %s', (source_id,))
        
        # Then delete the source
        cur.execute('DELETE FROM email_sources WHERE id = %s', (source_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect('/emails/view')
        
    except Exception as e:
        return str(e), 500

@app.route('/api/unprocessed-emails')
@token_required
def get_unprocessed_emails():
    """API endpoint to fetch unprocessed emails"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        cur.execute('''
            SELECT id, urls, body_html, received_at 
            FROM emails 
            WHERE processed = FALSE
            ORDER BY received_at DESC
        ''')
        
        emails = [dict(email) for email in cur.fetchall()]
        cur.close()
        conn.close()
        
        return jsonify(emails)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/mark-processed/<int:email_id>', methods=['POST'])
@token_required
def mark_email_processed(email_id):
    """API endpoint to mark email as processed"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            UPDATE emails 
            SET processed = TRUE 
            WHERE id = %s
        ''', (email_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"status": "success"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/parse-email', methods=['POST'])
def parse_email():
    print("==== Incoming SendGrid Parsed Email ====")
    print("Form data:", dict(request.form))

    try:
        # Get SendGrid's parsed fields
        to_addr = request.form.get('to', '')
        from_addr = request.form.get('from', '')
        subject = request.form.get('subject', '')
        text_body = request.form.get('text', '')
        html_body = request.form.get('html', '')
        
        # For forwarded emails, prefer HTML as it contains the forwarding format
        if html_body:
            email_body = html_body
        else:
            email_body = text_body
        
        # Extract URLs from text content first, fall back to HTML if no text
        urls = extract_urls(text_body) if text_body else extract_urls(html_body)

        # Find the source based on the to_address
        conn = get_db_connection()
        cur = conn.cursor()
        
        # First check if we have a source for this email address
        cur.execute('SELECT id FROM email_sources WHERE email_address = %s', (to_addr,))
        source_result = cur.fetchone()
        source_id = source_result[0] if source_result else None
        
        # If no source exists, create one automatically
        if not source_id:
            cur.execute('''
                INSERT INTO email_sources (name, email_address, description)
                VALUES (%s, %s, %s)
                RETURNING id
            ''', (from_addr.split('@')[1], to_addr, f'Auto-created from {from_addr}'))
            source_id = cur.fetchone()[0]

        # Insert into database
        cur.execute('''
            INSERT INTO emails (
                source_id, to_address, from_address, subject, body_text, body_html, urls, received_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            source_id,
            to_addr,
            from_addr,
            subject,
            text_body,
            email_body,
            urls,
            datetime.now()
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        print(f"Processed email: {subject}")
        return jsonify({"status": "success", "id": new_id}), 200

    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/emails/view')
def view_emails_html():
    """Render the main email dashboard."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Get all sources
        cur.execute('SELECT * FROM email_sources ORDER BY name')
        sources = cur.fetchall()
        
        # Get current source from query params or default to 'all'
        current_source = request.args.get('source', 'all')
        if current_source != 'all':
            current_source = int(current_source)
        
        sort = request.args.get('sort', 'newest')
        limit = request.args.get('limit', '10')
        time_filter = request.args.get('time', 'all')
        
        query = 'SELECT * FROM emails'
        params = []
        
        # Add source filter
        if current_source != 'all':
            query += ' WHERE source_id = %s'
            params.append(current_source)
        
        if time_filter == 'week':
            query += ' AND ' if params else ' WHERE '
            query += 'received_at >= NOW() - INTERVAL \'7 days\''
        elif time_filter == 'month':
            query += ' AND ' if params else ' WHERE '
            query += 'received_at >= NOW() - INTERVAL \'30 days\''
        
        query += ' ORDER BY received_at ' + ('DESC' if sort == 'newest' else 'ASC')
        query += ' LIMIT %s'
        params.append(int(limit))
        
        cur.execute(query, params)
        emails = cur.fetchall()
        cur.close()
        conn.close()

        emails_list = [process_email_data(dict(email)) for email in emails]
        sources_list = [dict(source) for source in sources]

        return render_template('emails.html', 
                             emails=emails_list,
                             sources=sources_list,
                             current_source=current_source,
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
        
        # Only return the email content portion for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render_template('email_single.html', email=email_dict)
        
        # For direct access, return the full page with just this email
        return render_template('emails.html', 
                             emails=[email_dict],
                             current_sort='newest',
                             current_limit='10',
                             current_time='all')

    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

# Initialize the database when the app starts
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
