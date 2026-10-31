from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_notice():
    data = request.get_json()
    text = data.get('text', '')
    
    if not text.strip():
        return jsonify({"error": "Notice text cannot be empty."}), 400

    # Heuristic extraction logic (simulating intelligent parsing)
    # 1. Extract dates / deadlines
    date_pattern = r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
    deadlines = list(set(re.findall(date_pattern, text, re.IGNORECASE)))
    
    # 2. Extract potential action keywords
    action_keywords = ["submit", "pay", "register", "vacate", "apply", "download", "contact", "attend"]
    found_actions = []
    sentences = re.split(r'[.!?]', text)
    for sentence in sentences:
        if any(keyword in sentence.lower() for keyword in action_keywords):
            cleaned = sentence.strip()
            if cleaned and cleaned not in found_actions:
                found_actions.append(cleaned)

    # 3. Generate summary headline
    summary = "Public notice processed. Review the key deadlines and required actions below."

    return jsonify({
        "summary": summary,
        "deadlines": deadlines if deadlines else ["No specific calendar date found. Please check document details."],
        "actions": found_actions if found_actions else ["Review the full text for specific instructions."]
    })

if __name__ == '__main__':
    print("Starting CivicLens web server on http://localhost:5000 ...")
    app.run(debug=True, port=5000)

