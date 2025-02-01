from flask import Flask, request, jsonify
from datetime import datetime
import os
import re  # For URL extraction

app = Flask(__name__)

# Store emails in memory (in production, use a database)
emails = []

def extract_urls(text):
    """Extract URLs from text using regex"""
    # This pattern matches most common URL formats
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
        
        # Get email data from SendGrid
        email_data = {
            'to': request.form.get('to', ''),
            'from': request.form.get('from', ''),
            'subject': request.form.get('subject', ''),
            'text': email_text,
            'urls': urls,  # Add extracted URLs
            'received_at': datetime.now().isoformat()
        }
        
        # Store the email
        emails.append(email_data)
        print(f"Received email: {email_data['subject']}")
        print(f"Found URLs: {urls}")
        
        return 'OK', 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/emails', methods=['GET'])
def view_emails():
    """View all received emails - for testing"""
    return jsonify(emails)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)