from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import cv2
import numpy as np
import base64
import uuid
import sqlite3
import json
import os
from datetime import datetime
from deepface import DeepFace

app = Flask(__name__, template_folder='../frontend/templates')
app.config['SECRET_KEY'] = 'ai-meeting-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure the reports directory exists
if not os.path.exists('../reports'):
    os.makedirs('../reports')

# Initialize database
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS meetings (
        id TEXT PRIMARY KEY,
        host_id TEXT,
        name TEXT,
        created_at TIMESTAMP
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id TEXT,
        user_id TEXT,
        name TEXT,
        joined_at TIMESTAMP,
        FOREIGN KEY (meeting_id) REFERENCES meetings (id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS engagement_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id TEXT,
        user_id TEXT,
        timestamp TIMESTAMP,
        engagement_score REAL,
        status TEXT,
        emotions TEXT,
        FOREIGN KEY (meeting_id) REFERENCES meetings (id)
    )
    ''')
    conn.commit()
    conn.close()

init_db()

# Active meetings store
active_meetings = {}
user_rooms = {}

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_meeting', methods=['POST'])
def create_meeting():
    meeting_name = request.form.get('meeting_name')
    host_name = request.form.get('host_name')
    
    # Generate meeting ID
    meeting_id = str(uuid.uuid4())[:8]
    user_id = str(uuid.uuid4())
    
    # Store in database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO meetings (id, host_id, name, created_at) VALUES (?, ?, ?, ?)",
        (meeting_id, user_id, meeting_name, datetime.now())
    )
    cursor.execute(
        "INSERT INTO participants (meeting_id, user_id, name, joined_at) VALUES (?, ?, ?, ?)",
        (meeting_id, user_id, host_name, datetime.now())
    )
    conn.commit()
    conn.close()
    
    # Initialize active meeting data
    active_meetings[meeting_id] = {
        'host_id': user_id,
        'participants': {user_id: {'name': host_name, 'engagement_status': 'Active'}}
    }
    
    return redirect(url_for('meeting', meeting_id=meeting_id, user_id=user_id, name=host_name))

@app.route('/join_meeting', methods=['POST'])
def join_meeting():
    meeting_id = request.form.get('meeting_id')
    participant_name = request.form.get('participant_name')
    
    # Check if meeting exists
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM meetings WHERE id = ?", (meeting_id,))
    meeting = cursor.fetchone()
    
    if not meeting:
        conn.close()
        return "Meeting not found", 404
    
    # Generate user ID and add participant
    user_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO participants (meeting_id, user_id, name, joined_at) VALUES (?, ?, ?, ?)",
        (meeting_id, user_id, participant_name, datetime.now())
    )
    conn.commit()
    conn.close()
    
    # Add to active meeting if exists
    if meeting_id in active_meetings:
        active_meetings[meeting_id]['participants'][user_id] = {
            'name': participant_name,
            'engagement_status': 'Active'
        }
    
    return redirect(url_for('meeting', meeting_id=meeting_id, user_id=user_id, name=participant_name))

@app.route('/meeting')
def meeting():
    meeting_id = request.args.get('meeting_id')
    user_id = request.args.get('user_id')
    name = request.args.get('name')
    
    if not meeting_id or not user_id or not name:
        return redirect(url_for('index'))
    
    # Check if meeting exists in database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM meetings WHERE id = ?", (meeting_id,))
    meeting = cursor.fetchone()
    conn.close()
    
    if not meeting:
        return redirect(url_for('index'))
    
    # Initialize meeting in active_meetings if not exists
    if meeting_id not in active_meetings:
        active_meetings[meeting_id] = {
            'host_id': None,  # Will be updated when host joins
            'participants': {}
        }
    
    return render_template('meeting.html', 
                          meeting_id=meeting_id, 
                          user_id=user_id, 
                          name=name,
                          meeting_name=meeting[1])

# Socket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('join')
def handle_join(data):
    meeting_id = data['meeting_id']
    user_id = data['user_id']
    name = data['name']
    
    join_room(meeting_id)
    user_rooms[request.sid] = meeting_id
    
    # Add participant to active meeting
    if meeting_id in active_meetings:
        if user_id not in active_meetings[meeting_id]['participants']:
            active_meetings[meeting_id]['participants'][user_id] = {
                'name': name,
                'engagement_status': 'Active'
            }
    
    # Notify others of join
    emit('user_joined', {
        'user_id': user_id,
        'name': name
    }, room=meeting_id)
    
    # Send current participants to new user
    if meeting_id in active_meetings:
        emit('participants_list', {
            'participants': active_meetings[meeting_id]['participants']
        }, room=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in user_rooms:
        meeting_id = user_rooms[request.sid]
        del user_rooms[request.sid]
        # Clean up would happen here
        emit('user_left', {'user_id': request.sid}, room=meeting_id)

@socketio.on('frame_data')
def handle_frame_data(data):
    meeting_id = data['meeting_id']
    user_id = data['user_id']
    frame_data = data['frame']
    
    # Convert base64 to cv2 image
    try:
        encoded_data = frame_data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Process frame with AI
        engagement_data = analyze_engagement(img)
        
        # Store engagement data
        store_engagement_data(meeting_id, user_id, engagement_data)
        
        # Broadcast engagement update
        emit('engagement_update', {
            'user_id': user_id,
            'engagement_status': engagement_data['status'],
            'engagement_score': engagement_data['score']
        }, room=meeting_id)
        
        # Update active meetings data
        if meeting_id in active_meetings and user_id in active_meetings[meeting_id]['participants']:
            active_meetings[meeting_id]['participants'][user_id]['engagement_status'] = engagement_data['status']
    
    except Exception as e:
        print(f"Error processing frame: {e}")

def analyze_engagement(frame):
    """Analyze engagement from video frame"""
    try:
        # Face detection
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        # If no face detected, return absent
        if len(faces) == 0:
            return {
                'score': 0.0,
                'status': 'Absent',
                'emotions': json.dumps({'neutral': 1.0})
            }
        
        # Get largest face
        largest_face = max(faces, key=lambda face: face[2] * face[3])
        x, y, w, h = largest_face
        
        # Extract face region
        face_img = frame[y:y+h, x:x+w]
        
        # Analyze emotion with deepface
        emotion_analysis = DeepFace.analyze(face_img, actions=['emotion'], enforce_detection=False)
        emotions = emotion_analysis[0]['emotion']
        
        # Calculate engagement score based on emotions
        engagement_score = calculate_engagement_score(emotions)
        
        # Determine status
        if engagement_score > 0.7:
            status = 'Active'
        elif engagement_score > 0.3:
            status = 'Distracted'
        else:
            status = 'Disengaged'
            
        return {
            'score': engagement_score,
            'status': status,
            'emotions': json.dumps(emotions)
        }
    
    except Exception as e:
        print(f"Error in engagement analysis: {e}")
        return {
            'score': 0.5,  # Neutral score
            'status': 'Unknown',
            'emotions': json.dumps({'neutral': 1.0})
        }

def calculate_engagement_score(emotions):
    """Calculate engagement score based on emotions"""
    # Higher weight for attentive emotions
    engagement_weights = {
        'happy': 0.9,
        'surprise': 0.8,
        'neutral': 0.7,
        'fear': 0.4,
        'sad': 0.3,
        'angry': 0.2,
        'disgust': 0.1
    }
    
    score = 0
    for emotion, value in emotions.items():
        score += value * engagement_weights.get(emotion.lower(), 0.5)
    
    return min(1.0, score)  # Cap at 1.0

def store_engagement_data(meeting_id, user_id, engagement_data):
    """Store engagement data in database"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO engagement_data (meeting_id, user_id, timestamp, engagement_score, status, emotions) VALUES (?, ?, ?, ?, ?, ?)",
            (meeting_id, user_id, datetime.now(), engagement_data['score'], engagement_data['status'], engagement_data['emotions'])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error storing engagement data: {e}")

@app.route('/get_meeting_stats', methods=['GET'])
def get_meeting_stats():
    meeting_id = request.args.get('meeting_id')
    
    if not meeting_id:
        return jsonify({'error': 'Meeting ID required'}), 400
    
    try:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get participant data
        cursor.execute("""
            SELECT p.user_id, p.name, 
                   (SELECT status FROM engagement_data 
                    WHERE user_id = p.user_id AND meeting_id = p.meeting_id 
                    ORDER BY timestamp DESC LIMIT 1) as current_status,
                   (SELECT AVG(engagement_score) FROM engagement_data 
                    WHERE user_id = p.user_id AND meeting_id = p.meeting_id) as avg_score
            FROM participants p
            WHERE p.meeting_id = ?
        """, (meeting_id,))
        
        participants = []
        for row in cursor.fetchall():
            participants.append({
                'user_id': row['user_id'],
                'name': row['name'],
                'status': row['current_status'] or 'Unknown',
                'avg_score': float(row['avg_score'] or 0)
            })
            
        # Get overall meeting stats
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT user_id) as total_participants,
                (SELECT COUNT(*) FROM engagement_data 
                 WHERE meeting_id = ? AND status = 'Active') as active_count,
                (SELECT COUNT(*) FROM engagement_data 
                 WHERE meeting_id = ? AND status = 'Distracted') as distracted_count,
                (SELECT COUNT(*) FROM engagement_data 
                 WHERE meeting_id = ? AND status = 'Disengaged') as disengaged_count,
                (SELECT COUNT(*) FROM engagement_data 
                 WHERE meeting_id = ? AND status = 'Absent') as absent_count,
                (SELECT AVG(engagement_score) FROM engagement_data 
                 WHERE meeting_id = ?) as avg_meeting_score
            FROM participants
            WHERE meeting_id = ?
        """, (meeting_id, meeting_id, meeting_id, meeting_id, meeting_id, meeting_id))
        
        stats = cursor.fetchone()
        
        meeting_stats = {
            'total_participants': stats['total_participants'],
            'status_counts': {
                'Active': stats['active_count'] or 0,
                'Distracted': stats['distracted_count'] or 0,
                'Disengaged': stats['disengaged_count'] or 0,
                'Absent': stats['absent_count'] or 0
            },
            'avg_meeting_score': float(stats['avg_meeting_score'] or 0),
            'participants': participants
        }
        
        conn.close()
        return jsonify(meeting_stats)
    
    except Exception as e:
        print(f"Error getting meeting stats: {e}")
        return jsonify({'error': 'Failed to retrieve meeting statistics'}), 500

@app.route('/end_meeting', methods=['POST'])
def end_meeting():
    meeting_id = request.form.get('meeting_id')
    user_id = request.form.get('user_id')
    
    # Verify user is host
    if meeting_id in active_meetings and active_meetings[meeting_id]['host_id'] == user_id:
        # Generate report
        generate_meeting_report(meeting_id)
        
        # Clean up
        if meeting_id in active_meetings:
            del active_meetings[meeting_id]
        
        return jsonify({'success': True, 'report': f'../reports/{meeting_id}_report.json'})
    
    return jsonify({'error': 'Unauthorized'}), 403

def generate_meeting_report(meeting_id):
    """Generate JSON report for the meeting"""
    try:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get meeting info
        cursor.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
        meeting = dict(cursor.fetchone())
        
        # Get participants
        cursor.execute("SELECT * FROM participants WHERE meeting_id = ?", (meeting_id,))
        participants = [dict(row) for row in cursor.fetchall()]
        
        # Get engagement data
        cursor.execute("""
            SELECT user_id, 
                   AVG(engagement_score) as avg_score,
                   COUNT(CASE WHEN status = 'Active' THEN 1 END) as active_count,
                   COUNT(CASE WHEN status = 'Distracted' THEN 1 END) as distracted_count,
                   COUNT(CASE WHEN status = 'Disengaged' THEN 1 END) as disengaged_count,
                   COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_count
            FROM engagement_data
            WHERE meeting_id = ?
            GROUP BY user_id
        """, (meeting_id,))
        
        engagement_summary = {}
        for row in cursor.fetchall():
            engagement_summary[row['user_id']] = {
                'avg_score': float(row['avg_score']),
                'status_counts': {
                    'Active': row['active_count'],
                    'Distracted': row['distracted_count'],
                    'Disengaged': row['disengaged_count'],
                    'Absent': row['absent_count']
                }
            }
        
        # Generate timeline data
        cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:%M:%S', timestamp) as time_interval,
                   AVG(engagement_score) as avg_score,
                   COUNT(CASE WHEN status = 'Active' THEN 1 END) as active_count,
                   COUNT(CASE WHEN status = 'Distracted' THEN 1 END) as distracted_count,
                   COUNT(CASE WHEN status = 'Disengaged' THEN 1 END) as disengaged_count,
                   COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_count
            FROM engagement_data
            WHERE meeting_id = ?
            GROUP BY time_interval
            ORDER BY time_interval
        """, (meeting_id,))
        
        timeline = [dict(row) for row in cursor.fetchall()]
        
        # Overall meeting statistics
        cursor.execute("""
            SELECT AVG(engagement_score) as avg_meeting_score,
                   COUNT(CASE WHEN status = 'Active' THEN 1 END) * 100.0 / COUNT(*) as active_percentage,
                   COUNT(CASE WHEN status = 'Distracted' THEN 1 END) * 100.0 / COUNT(*) as distracted_percentage,
                   COUNT(CASE WHEN status = 'Disengaged' THEN 1 END) * 100.0 / COUNT(*) as disengaged_percentage,
                   COUNT(CASE WHEN status = 'Absent' THEN 1 END) * 100.0 / COUNT(*) as absent_percentage
            FROM engagement_data
            WHERE meeting_id = ?
        """, (meeting_id,))
        
        overall_stats = dict(cursor.fetchone())
        
        # Compile report
        report = {
            'meeting_id': meeting_id,
            'meeting_name': meeting['name'],
            'created_at': meeting['created_at'],
            'host_id': meeting['host_id'],
            'participants': participants,
            'engagement_summary': engagement_summary,
            'timeline': timeline,
            'overall_stats': {
                'avg_meeting_score': float(overall_stats['avg_meeting_score'] or 0),
                'status_percentages': {
                    'Active': float(overall_stats['active_percentage'] or 0),
                    'Distracted': float(overall_stats['distracted_percentage'] or 0),
                    'Disengaged': float(overall_stats['disengaged_percentage'] or 0),
                    'Absent': float(overall_stats['absent_percentage'] or 0)
                }
            }
        }
        
        conn.close()
        
        # Save to file
        with open(f'../reports/{meeting_id}_report.json', 'w') as f:
            json.dump(report, f, indent=4)
        
        return report
    
    except Exception as e:
        print(f"Error generating meeting report: {e}")
        return None

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)