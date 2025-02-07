from flask import Flask, request, jsonify, render_template, Response, redirect
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
import json
from functools import wraps

app = Flask(__name__)

# ======== START OF NEW CODE ========
# Authentication decorator for API endpoints
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_token = request.headers.get('Authorization')
        if not auth_token or auth_token != f"Bearer {os.environ.get('API_TOKEN')}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# New database column for processing status
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Existing table creation code...
    
    # Add processed column to emails table
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'emails' AND column_name = 'processed'
        );
    """)
    column_exists = cur.fetchone()[0]
    
    if not column_exists:
        cur.execute('ALTER TABLE emails ADD COLUMN processed BOOLEAN DEFAULT FALSE;')
    
    conn.commit()
    cur.close()
    conn.close()

# New API endpoint to get unprocessed emails
@app.route('/api/unprocessed-emails', methods=['GET'])
@token_required
def get_unprocessed_emails():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        cur.execute('''
            SELECT id, urls, body_html, received_at, subject, from_address
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

# New API endpoint to mark emails as processed
@app.route('/api/mark-processed', methods=['POST'])
@token_required
def mark_processed():
    try:
        email_ids = request.json.get('email_ids', [])
        if not email_ids:
            return jsonify({"error": "No email IDs provided"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            UPDATE emails 
            SET processed = TRUE 
            WHERE id = ANY(%s)
        ''', (email_ids,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"message": f"Marked {len(email_ids)} emails as processed"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ======== END OF NEW CODE ========

# Existing functions below (no changes needed to these)
def get_db_connection():
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    return conn

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

# Existing routes below (no changes needed to these)
@app.route('/')
def home():
    return redirect('/emails/view')

@app.route('/sources/add', methods=['POST'])
def add_source():
    # ... existing code ...

@app.route('/sources/delete/<int:source_id>', methods=['POST'])
def delete_source(source_id):
    # ... existing code ...

@app.route('/parse-email', methods=['POST'])
def parse_email():
    # ... existing code ...

@app.route('/emails/view')
def view_emails_html():
    # ... existing code ...

@app.route('/emails/view/<int:email_id>')
def view_single_email(email_id):
    # ... existing code ...

# Initialize the database when the app starts
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
