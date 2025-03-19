# AI-based Behavior Analysis System for Online Meetings

This project creates an online meeting platform with AI-based participant behavior analysis. The system detects participant engagement through facial expressions, head movements, and screen activity. It helps determine if users are actively engaged, distracted, or absent during a meeting.

## Features

- **Online Meeting System** - Users can create and join meetings via a shared link.
- **Face Detection** - Identifies if the participant is present.
- **Eye & Head Movement Tracking** - Monitors attention and distractions.
- **Facial Expression Analysis** - Detects engagement levels (e.g., attentive, distracted, sleepy).
- **Engagement Score** - Calculates and displays attentiveness levels.
- **Dashboard & Reports** - Shows live engagement stats and stores meeting data.

## Tech Stack

- **Frontend:** HTML, CSS, JavaScript (Embedded in HTML)
- **Backend:** Flask (Python)
- **WebRTC:** For video streaming
- **AI Models:** OpenCV (Face tracking), DeepFace (Emotion detection)
- **Database:** SQLite (To store engagement data)
- **Execution:** Runs locally via Flask

## Setup Instructions

1. Clone the repository:
   ```
   git clone https://github.com/maaazzinn/Meet-Mood.git
   cd Meet-Mood
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the application:
   ```
   cd backend
   python app.py
   ```

4. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

## Usage

1. **Create a Meeting**:
   - Enter a meeting name and your name
   - Click "Create Meeting"
   - Share the meeting ID with participants

2. **Join a Meeting**:
   - Enter the meeting ID and your name
   - Click "Join Meeting"

3. **During the Meeting**:
   - The system will analyze your engagement levels in real-time
   - A dashboard shows the engagement status of all participants
   - Meeting hosts can end the meeting and generate reports

## Folder Structure

```
AI-Meeting-Engagement-System/
│-- backend/
│   │-- app.py  # Main backend with WebRTC & AI analysis
│   │-- database.db  # SQLite database
│-- frontend/
│   │-- templates/
│   │   │-- index.html  # Main page with embedded CSS & JS
│   │   │-- meeting.html  # Meeting room interface
│-- reports/  # Logs & engagement reports
│-- requirements.txt  # Python dependencies
│-- README.md  # Project documentation
```

## Engagement Classification

The system classifies participants into four engagement levels:

- **Active**: Fully engaged in the meeting
- **Distracted**: Temporarily not focusing on the meeting
- **Disengaged**: Not engaged for an extended period
- **Absent**: Not present in front of the camera

## License

This project is licensed under the MIT License - see the LICENSE file for details.
