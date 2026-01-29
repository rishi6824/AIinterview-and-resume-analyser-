from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import json
from datetime import datetime
from config import Config
from models.ai_interviewer import AIInterviewer
from models.speech_processor import SpeechProcessor
from models.question_generator import QuestionGenerator
from models.physical_analyzer import PhysicalAnalyzer
from utils.helpers import allowed_file, calculate_score, clean_text
import secrets
import ssl

app = Flask(__name__)
app.config.from_object(Config)

# Create upload directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize AI components
ai_interviewer = AIInterviewer()
speech_processor = SpeechProcessor()
question_generator = QuestionGenerator()
physical_analyzer = PhysicalAnalyzer()

# Add CORS headers for microphone access
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_video_interview', methods=['POST'])
def start_video_interview():
    session.clear()
    
    # Get job role
    job_role = request.form.get('job_role', 'software_engineer')
    resume_analysis = session.get('resume_analysis', {})
    
    # Initialize interview session first
    session['interview_id'] = secrets.token_hex(16)
    session['current_question'] = 0
    session['score'] = 0
    session['responses'] = []
    session['job_role'] = job_role
    session['start_time'] = datetime.now().isoformat()
    session['enable_voice'] = True
    
    # Generate 10-15 personalized questions using Hugging Face API
    from config import Config
    num_questions = Config.DEFAULT_QUESTIONS
    
    print(f"🔄 Generating {num_questions} questions for {job_role} interview using Hugging Face API...")
    questions = question_generator.generate_questions(job_role, resume_analysis, num_questions)
    
    # Ensure we have at least minimum questions
    if not questions or len(questions) < Config.MIN_QUESTIONS:
        print(f"⚠️ Only got {len(questions) if questions else 0} questions, generating more...")
        if not questions:
            questions = []
        
        # Generate more questions if needed
        remaining = Config.MIN_QUESTIONS - len(questions)
        additional = question_generator.generate_questions(job_role, resume_analysis, remaining)
        if additional:
            questions.extend(additional[:remaining])
    
    # Final fallback - use base questions if still not enough
    if not questions or len(questions) < Config.MIN_QUESTIONS:
        print("⚠️ Using fallback base questions...")
        base_questions = question_generator.base_questions.get(job_role, question_generator.base_questions["software_engineer"])
        # Repeat to reach minimum
        while len(base_questions) < Config.MIN_QUESTIONS:
            base_questions.extend(question_generator.base_questions.get(job_role, question_generator.base_questions["software_engineer"]))
        questions = base_questions[:Config.MIN_QUESTIONS]
    
    session['questions'] = questions
    print(f"✅ Successfully generated {len(questions)} questions for {job_role} interview")
    
    # Log first few questions for debugging
    if questions:
        print(f"📝 Sample questions:")
        for i, q in enumerate(questions[:3]):
            print(f"   {i+1}. {q.get('question', 'N/A')[:60]}...")
    
    return redirect(url_for('video_interview'))

@app.route('/video_interview')
def video_interview():
    if 'interview_id' not in session:
        return redirect(url_for('index'))
    
    # Ensure questions are generated before showing video interview page
    if 'questions' not in session or not session['questions']:
        print("⚠️ No questions in video_interview route - redirecting to generate questions...")
        job_role = session.get('job_role', 'software_engineer')
        resume_analysis = session.get('resume_analysis', {})
        
        from config import Config
        num_questions = Config.DEFAULT_QUESTIONS
        
        questions = question_generator.generate_questions(job_role, resume_analysis, num_questions)
        
        if not questions or len(questions) < Config.MIN_QUESTIONS:
            if not questions:
                questions = []
            remaining = Config.MIN_QUESTIONS - len(questions)
            additional = question_generator.generate_questions(job_role, resume_analysis, remaining)
            if additional:
                questions.extend(additional[:remaining])
        
        if not questions or len(questions) < Config.MIN_QUESTIONS:
            base_questions = question_generator.base_questions.get(job_role, question_generator.base_questions["software_engineer"])
            while len(base_questions) < Config.MIN_QUESTIONS:
                base_questions.extend(question_generator.base_questions.get(job_role, question_generator.base_questions["software_engineer"]))
            questions = base_questions[:Config.MIN_QUESTIONS]
        
        session['questions'] = questions
        session['current_question'] = 0
        print(f"✅ Generated {len(questions)} questions in video_interview route")
    
    return render_template('video_interview.html',
                         enable_voice=session.get('enable_voice', True))

@app.route('/interview_room')
def interview_room():
    if 'interview_id' not in session:
        return redirect(url_for('index'))
    
    # Auto-generate questions if they don't exist
    if 'questions' not in session or not session['questions']:
        print("⚠️ No questions found in session - auto-generating questions...")
        job_role = session.get('job_role', 'software_engineer')
        resume_analysis = session.get('resume_analysis', {})
        
        from config import Config
        num_questions = Config.DEFAULT_QUESTIONS
        
        # Generate questions using Hugging Face API
        questions = question_generator.generate_questions(job_role, resume_analysis, num_questions)
        
        # Ensure we have at least minimum questions
        if not questions or len(questions) < Config.MIN_QUESTIONS:
            print(f"⚠️ Only got {len(questions) if questions else 0} questions, generating more...")
            # Try generating more questions
            if not questions:
                questions = []
            
            remaining = Config.MIN_QUESTIONS - len(questions)
            additional = question_generator.generate_questions(job_role, resume_analysis, remaining)
            if additional:
                questions.extend(additional[:remaining])
        
        # Final check - if still no questions, use fallback
        if not questions or len(questions) < Config.MIN_QUESTIONS:
            print("⚠️ Using fallback questions...")
            # Get base questions as fallback
            base_questions = question_generator.base_questions.get(job_role, question_generator.base_questions["software_engineer"])
            # Repeat to reach minimum
            while len(base_questions) < Config.MIN_QUESTIONS:
                base_questions.extend(question_generator.base_questions.get(job_role, question_generator.base_questions["software_engineer"]))
            questions = base_questions[:Config.MIN_QUESTIONS]
        
        session['questions'] = questions
        session['current_question'] = 0
        print(f"✅ Auto-generated {len(questions)} questions for {job_role} interview")
    
    current_q = session['current_question']
    questions = session['questions']
    
    # Check if interview is completed - auto redirect to results
    if current_q >= len(questions):
        # Stop any ongoing analysis and redirect to results
        return redirect(url_for('results'))
    
    question = questions[current_q]
    return render_template('interview_room.html',
                         question=question,
                         question_num=current_q + 1,
                         total_questions=len(questions),
                         enable_voice=session.get('enable_voice', True))

@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    if 'interview_id' not in session:
        return jsonify({'error': 'No active interview'}), 400
    
    current_q = session['current_question']
    questions = session['questions']
    
    # Check if we've exceeded the question count
    if current_q >= len(questions):
        return jsonify({
            'completed': True,
            'next_question': current_q,
            'score': 0,
            'feedback': 'Interview completed!',
            'detailed_analysis': {}
        })
    
    answer = request.form.get('answer', '')
    job_role = session['job_role']
    resume_analysis = session.get('resume_analysis', {})
    
    # Get physical analysis data if available
    physical_data = session.get('physical_analysis', {}).get(f'question_{current_q}', {})
    
    # Analyze the answer
    score, feedback, detailed_analysis = ai_interviewer.analyze_answer(
        job_role, current_q, answer, resume_analysis
    )
    
    # Integrate physical analysis into score if available
    if physical_data and Config.ENABLE_PHYSICAL_ANALYSIS:
        physical_score = physical_data.get('overall_physical_score', 0)
        # Combine answer score (70%) with physical score (30%)
        combined_score = (score * 0.7) + (physical_score * 0.3)
        score = round(combined_score, 1)
        
        # Add physical analysis to detailed analysis
        detailed_analysis['physical_analysis'] = physical_data
        detailed_analysis['confidence_score'] = physical_data.get('confidence', 0)
        detailed_analysis['voice_quality'] = physical_data.get('voice_quality', 0)
        detailed_analysis['body_language'] = physical_data.get('body_language', 0)
    
    # Add AI personality to feedback
    if score >= 8:
        ai_feedback = f"Excellent! {feedback} That was a well-structured response."
    elif score >= 6:
        ai_feedback = f"Good job. {feedback} You're on the right track."
    elif score >= 4:
        ai_feedback = f"Okay. {feedback} Let's work on improving this."
    else:
        ai_feedback = f"I see. {feedback} We'll practice more on this area."
    
    # Store response with physical analysis
    response_data = {
        'question_index': current_q,
        'question': questions[current_q]['question'],
        'answer': answer,
        'score': score,
        'feedback': ai_feedback,
        'detailed_analysis': detailed_analysis
    }
    
    # Add physical analysis if available
    if physical_data:
        response_data['physical_analysis'] = physical_data
    
    session['responses'].append(response_data)
    
    # Clear physical analysis for next question
    if f'question_{current_q}' in session.get('physical_analysis', {}):
        session['physical_analysis'].pop(f'question_{current_q}', None)
    
    session['score'] += score
    session['current_question'] += 1
    
    # Check if interview is completed
    completed = session['current_question'] >= len(questions)
    
    return jsonify({
        'next_question': session['current_question'],
        'score': score,
        'feedback': ai_feedback,
        'detailed_analysis': detailed_analysis,
        'completed': completed
    })

@app.route('/process_voice', methods=['POST'])
def process_voice():
    if 'interview_id' not in session:
        return jsonify({'error': 'No active interview'}), 400
    
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file'}), 400
    
    audio_file = request.files['audio']
    
    try:
        # Convert speech to text
        text = speech_processor.speech_to_text(audio_file)
        
        if text:
            return jsonify({
                'success': True,
                'text': text
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not understand audio'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/analyze_physical', methods=['POST'])
def analyze_physical():
    """Analyze physical actions: confidence, voice, body language"""
    if 'interview_id' not in session:
        return jsonify({'error': 'No active interview'}), 400
    
    try:
        current_q = session['current_question']
        
        # Get video frames and audio segments from request
        video_frames = request.form.getlist('video_frames[]')  # Base64 encoded frames
        audio_segments = request.form.getlist('audio_segments[]')  # Base64 encoded audio
        
        if not video_frames and not audio_segments:
            return jsonify({'error': 'No data provided'}), 400
        
        # Analyze physical actions using Hugging Face
        physical_analysis = physical_analyzer.analyze_realtime_data(
            video_frames if video_frames else [],
            audio_segments if audio_segments else []
        )
        
        # Store analysis in session for this question
        if 'physical_analysis' not in session:
            session['physical_analysis'] = {}
        
        session['physical_analysis'][f'question_{current_q}'] = physical_analysis
        
        return jsonify({
            'success': True,
            'analysis': physical_analysis,
            'summary': physical_analyzer.get_analysis_summary()
        })
        
    except Exception as e:
        print(f"Error in physical analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/update_physical_analysis', methods=['POST'])
def update_physical_analysis():
    """Update physical analysis with single frame/audio segment"""
    if 'interview_id' not in session:
        return jsonify({'error': 'No active interview'}), 400
    
    try:
        current_q = session['current_question']
        
        # Get single frame or audio segment
        video_frame = request.form.get('video_frame')  # Base64 encoded
        audio_segment = request.form.get('audio_segment')  # Base64 encoded
        
        if not video_frame and not audio_segment:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        # Initialize storage if needed
        if 'physical_analysis' not in session:
            session['physical_analysis'] = {}
        
        if f'question_{current_q}' not in session['physical_analysis']:
            session['physical_analysis'][f'question_{current_q}'] = {
                'confidence': 0.0,
                'voice_quality': 0.0,
                'body_language': 0.0,
                'overall_physical_score': 0.0,
                'details': {
                    'confidence_scores': [],
                    'voice_scores': [],
                    'posture_scores': [],
                    'frame_count': 0,
                    'audio_segment_count': 0
                }
            }
        
        current_data = session['physical_analysis'][f'question_{current_q}']
        details = current_data['details']
        
        # Analyze video frame if provided
        if video_frame:
            frame_analysis = physical_analyzer.analyze_video_frame(video_frame)
            if frame_analysis:
                details['confidence_scores'].append(frame_analysis.get('confidence', 5.0))
                details['posture_scores'].append(frame_analysis.get('posture_score', 5.0))
                details['frame_count'] += 1
                
                # Recalculate averages
                if details['confidence_scores']:
                    current_data['confidence'] = round(
                        sum(details['confidence_scores']) / len(details['confidence_scores']), 2
                    )
                if details['posture_scores']:
                    current_data['body_language'] = round(
                        sum(details['posture_scores']) / len(details['posture_scores']), 2
                    )
        
        # Analyze audio segment if provided
        if audio_segment:
            audio_analysis = physical_analyzer.analyze_audio(audio_segment)
            if audio_analysis:
                details['voice_scores'].append(audio_analysis.get('voice_score', 5.0))
                details['audio_segment_count'] += 1
                
                # Recalculate average
                if details['voice_scores']:
                    current_data['voice_quality'] = round(
                        sum(details['voice_scores']) / len(details['voice_scores']), 2
                    )
        
        # Recalculate overall physical score
        current_data['overall_physical_score'] = round(
            (current_data['confidence'] * Config.CONFIDENCE_WEIGHT +
             current_data['voice_quality'] * Config.VOICE_WEIGHT +
             current_data['body_language'] * Config.BODY_LANGUAGE_WEIGHT), 2
        )
        
        return jsonify({
            'success': True,
            'current_analysis': current_data,
            'summary': {
                'confidence': current_data['confidence'],
                'voice_quality': current_data['voice_quality'],
                'body_language': current_data['body_language'],
                'overall_physical_score': current_data['overall_physical_score']
            }
        })
        
    except Exception as e:
        print(f"Error updating physical analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/results')
def results():
    if 'interview_id' not in session:
        return redirect(url_for('index'))
    
    total_score = session['score']
    max_possible = len(session['responses']) * 10
    percentage = (total_score / max_possible * 100) if max_possible > 0 else 0
    
    # Generate overall feedback
    overall_feedback = ai_interviewer.generate_overall_feedback(
        session['responses'], session.get('resume_analysis', {})
    )
    
    return render_template('results.html',
                         score=total_score,
                         percentage=percentage,
                         responses=session['responses'],
                         overall_feedback=overall_feedback,
                         resume_analysis=session.get('resume_analysis'))

@app.route('/auto_next_question')
def auto_next_question():
    """Automatically redirect to next question or results"""
    if 'interview_id' not in session:
        return redirect(url_for('index'))
    
    current_q = session['current_question']
    questions = session['questions']
    
    if current_q >= len(questions):
        return redirect(url_for('results'))
    else:
        return redirect(url_for('interview_room'))

@app.route('/get_next_question')
def get_next_question():
    if 'interview_id' not in session:
        return jsonify({'error': 'No active interview'}), 400
    
    current_q = session['current_question']
    questions = session['questions']
    
    if current_q >= len(questions):
        return jsonify({'completed': True})
    
    question = questions[current_q]
    return jsonify({
        'question': question['question'],
        'question_num': current_q + 1,
        'total_questions': len(questions),
        'type': question.get('type', 'technical')
    })

def create_ssl_context():
    """Create SSL context with fallback"""
    try:
        # Method 1: Use existing certificate files
        if os.path.exists('cert.pem') and os.path.exists('key.pem'):
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.load_cert_chain('cert.pem', 'key.pem')
            return context
        else:
            # Method 2: Create self-signed certificate programmatically
            from OpenSSL import crypto
            import tempfile
            
            # Create a key pair
            k = crypto.PKey()
            k.generate_key(crypto.TYPE_RSA, 4096)
            
            # Create a self-signed cert
            cert = crypto.X509()
            cert.get_subject().C = "US"
            cert.get_subject().ST = "State"
            cert.get_subject().L = "City"
            cert.get_subject().O = "Organization"
            cert.get_subject().OU = "Organization Unit"
            cert.get_subject().CN = "localhost"
            cert.set_serial_number(1000)
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(365*24*60*60)
            cert.set_issuer(cert.get_subject())
            cert.set_pubkey(k)
            cert.sign(k, 'sha512')
            
            # Save certificate and key to temporary files
            with open('cert.pem', 'wt') as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode('utf-8'))
            with open('key.pem', 'wt') as f:
                f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode('utf-8'))
            
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.load_cert_chain('cert.pem', 'key.pem')
            return context
            
    except Exception as e:
        print(f"SSL context creation failed: {e}")
        return None

if __name__ == '__main__':
    # Try to run with HTTPS first
    ssl_context = create_ssl_context()
    
    if ssl_context:
        print("🚀 Interview Platform running with HTTPS on https://localhost:5000")
        print("📹 Camera and microphone should work now!")
        print("🔐 Make sure to access via: https://localhost:5000")
        app.run(debug=True, ssl_context=ssl_context, host='0.0.0.0', port=5000)
    else:
        print("⚠️  Running without HTTPS - camera/microphone won't work")
        print("💡 To fix this, run: openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 -subj '/C=US/ST=State/L=City/O=Organization/CN=localhost'")
        print("🚀 Interview Platform running on http://localhost:5000")
        app.run(debug=True, host='0.0.0.0', port=5000)
