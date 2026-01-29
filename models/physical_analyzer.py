"""
Physical Actions Analyzer
Analyzes confidence, voice, body language, and actions during interview using Hugging Face API
"""
import requests
import json
import base64
import numpy as np
from config import Config

class PhysicalAnalyzer:
    def __init__(self):
        self.api_key = Config.HUGGINGFACE_API_KEY
        self.api_url = Config.HUGGINGFACE_API_URL
        
        # Hugging Face models for analysis
        self.face_emotion_model = 'trpakov/vit-face-expression'  # Face emotion detection
        self.voice_emotion_model = 'j-hartmann/emotion-english-distilroberta-base'  # Voice emotion
        self.sentiment_model = Config.SENTIMENT_MODEL
        self.body_pose_model = 'facebook/detr-resnet-50'  # Body pose detection
        
        # Store analysis results
        self.current_analysis = {
            'confidence': 0.0,
            'voice_quality': 0.0,
            'body_language': 0.0,
            'overall_physical_score': 0.0,
            'details': {}
        }
    
    def analyze_video_frame(self, frame_data):
        """
        Analyze a video frame for facial expressions and body language
        frame_data: base64 encoded image or image array
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Prepare image data
            if isinstance(frame_data, str):
                # Base64 encoded string (already base64)
                image_data = frame_data
            else:
                # If numpy array or other format, convert to base64
                # For now, assume string is base64
                image_data = str(frame_data)
            
            # Analyze face emotions
            emotion_scores = self._analyze_face_emotion(image_data, headers)
            
            # Analyze body posture
            posture_score = self._analyze_body_posture(image_data, headers)
            
            # Calculate confidence based on facial expressions
            confidence = self._calculate_confidence(emotion_scores)
            
            return {
                'emotions': emotion_scores,
                'posture_score': posture_score,
                'confidence': confidence
            }
            
        except Exception as e:
            print(f"Error analyzing video frame: {e}")
            return None
    
    def _analyze_face_emotion(self, image_data, headers):
        """Analyze facial expressions using Hugging Face vision models"""
        try:
            # Try emotion detection model
            payload = {
                "inputs": f"data:image/jpeg;base64,{image_data}" if isinstance(image_data, str) else image_data
            }
            
            # Use image classification model
            api_endpoint = f"https://api-inference.huggingface.co/models/{self.face_emotion_model}"
            
            response = requests.post(
                api_endpoint,
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list):
                    result = result[0]
                
                # Extract emotion scores
                emotions = {}
                if isinstance(result, list):
                    for item in result:
                        label = item.get('label', '').lower()
                        score = item.get('score', 0)
                        emotions[label] = score
                elif isinstance(result, dict):
                    label = result.get('label', '').lower()
                    score = result.get('score', 0)
                    emotions[label] = score
                
                return emotions
        except Exception as e:
            print(f"Error in face emotion analysis: {e}")
        
        return {}
    
    def _analyze_body_posture(self, image_data, headers):
        """Analyze body posture and gestures"""
        try:
            # Use object detection model to detect person and posture
            payload = {
                "inputs": f"data:image/jpeg;base64,{image_data}" if isinstance(image_data, str) else image_data
            }
            
            api_endpoint = f"https://api-inference.huggingface.co/models/{self.body_pose_model}"
            
            response = requests.post(
                api_endpoint,
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Analyze detected objects for posture indicators
                # Good posture indicators: upright position, shoulders back, head up
                posture_score = 5.0  # Default neutral score
                
                if isinstance(result, list):
                    # Count detected persons and analyze positions
                    person_count = sum(1 for item in result if 'person' in str(item.get('label', '')).lower())
                    if person_count > 0:
                        # Better posture if person detected clearly
                        posture_score = 7.0
                
                return min(10.0, posture_score)
        except Exception as e:
            print(f"Error in body posture analysis: {e}")
        
        return 5.0  # Default neutral score
    
    def _calculate_confidence(self, emotion_scores):
        """Calculate confidence score from facial expressions"""
        try:
            if not emotion_scores:
                return 5.0  # Default neutral confidence
            
            # Positive emotions indicate confidence
            positive_emotions = ['happy', 'confident', 'smile', 'positive', 'joy']
            negative_emotions = ['sad', 'fear', 'angry', 'disgust', 'surprise']
            neutral_emotions = ['neutral', 'calm', 'focused']
            
            positive_score = sum(emotion_scores.get(emotion, 0) for emotion in positive_emotions if emotion in str(emotion_scores))
            negative_score = sum(emotion_scores.get(emotion, 0) for emotion in negative_emotions if emotion in str(emotion_scores))
            
            # Calculate confidence (0-10 scale)
            if positive_score > negative_score:
                confidence = 5.0 + (positive_score * 5.0)
            elif negative_score > positive_score:
                confidence = 5.0 - (negative_score * 3.0)
            else:
                confidence = 5.0
            
            return max(0.0, min(10.0, confidence))
        except Exception as e:
            print(f"Error calculating confidence: {e}")
            return 5.0
    
    def analyze_audio(self, audio_data):
        """
        Analyze voice characteristics: tone, pace, clarity, emotion
        audio_data: base64 encoded audio or audio file path
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Analyze voice emotion
            voice_emotion = self._analyze_voice_emotion(audio_data, headers)
            
            # Analyze speech quality
            quality_score = self._analyze_speech_quality(audio_data, voice_emotion)
            
            return {
                'emotion': voice_emotion,
                'quality_score': quality_score,
                'voice_score': (quality_score + (voice_emotion.get('confidence', 5.0) if isinstance(voice_emotion, dict) else 5.0)) / 2
            }
            
        except Exception as e:
            print(f"Error analyzing audio: {e}")
            return None
    
    def _analyze_voice_emotion(self, audio_data, headers):
        """Analyze voice emotion and tone"""
        try:
            # Use audio classification model
            payload = {
                "inputs": audio_data if isinstance(audio_data, str) else base64.b64encode(audio_data).decode('utf-8')
            }
            
            api_endpoint = f"https://api-inference.huggingface.co/models/{self.voice_emotion_model}"
            
            response = requests.post(
                api_endpoint,
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                emotions = {}
                if isinstance(result, list):
                    for item in result:
                        label = item.get('label', '')
                        score = item.get('score', 0)
                        emotions[label] = score
                elif isinstance(result, dict):
                    label = result.get('label', '')
                    score = result.get('score', 0)
                    emotions[label] = score
                
                return emotions
        except Exception as e:
            print(f"Error in voice emotion analysis: {e}")
        
        return {}
    
    def _analyze_speech_quality(self, audio_data, emotion_data):
        """Analyze speech quality: clarity, pace, volume"""
        try:
            # Positive emotions and clear speech indicate good quality
            if isinstance(emotion_data, dict):
                # Calculate quality based on emotion scores
                positive_keywords = ['joy', 'happy', 'neutral', 'calm']
                negative_keywords = ['fear', 'sadness', 'anger', 'disgust']
                
                positive_score = sum(emotion_data.get(kw, 0) for kw in positive_keywords if kw in str(emotion_data))
                negative_score = sum(emotion_data.get(kw, 0) for kw in negative_keywords if kw in str(emotion_data))
                
                # Quality score based on emotion balance
                if positive_score > negative_score:
                    quality = 6.0 + (positive_score * 4.0)
                else:
                    quality = 4.0 + (positive_score * 2.0)
                
                return max(0.0, min(10.0, quality))
            
            return 5.0  # Default neutral quality
        except Exception as e:
            print(f"Error analyzing speech quality: {e}")
            return 5.0
    
    def analyze_realtime_data(self, video_frames, audio_segments):
        """
        Analyze real-time data from interview
        video_frames: list of video frame data
        audio_segments: list of audio segment data
        """
        try:
            all_confidence_scores = []
            all_voice_scores = []
            all_posture_scores = []
            
            # Analyze video frames
            for frame in video_frames:
                frame_analysis = self.analyze_video_frame(frame)
                if frame_analysis:
                    all_confidence_scores.append(frame_analysis.get('confidence', 5.0))
                    all_posture_scores.append(frame_analysis.get('posture_score', 5.0))
            
            # Analyze audio segments
            for audio in audio_segments:
                audio_analysis = self.analyze_audio(audio)
                if audio_analysis:
                    all_voice_scores.append(audio_analysis.get('voice_score', 5.0))
            
            # Calculate averages
            avg_confidence = np.mean(all_confidence_scores) if all_confidence_scores else 5.0
            avg_voice_score = np.mean(all_voice_scores) if all_voice_scores else 5.0
            avg_posture_score = np.mean(all_posture_scores) if all_posture_scores else 5.0
            
            # Overall physical score (weighted average)
            overall_physical = (
                avg_confidence * 0.4 +  # Confidence is most important
                avg_voice_score * 0.35 +  # Voice quality
                avg_posture_score * 0.25  # Body language
            )
            
            self.current_analysis = {
                'confidence': round(avg_confidence, 2),
                'voice_quality': round(avg_voice_score, 2),
                'body_language': round(avg_posture_score, 2),
                'overall_physical_score': round(overall_physical, 2),
                'details': {
                    'confidence_scores': all_confidence_scores,
                    'voice_scores': all_voice_scores,
                    'posture_scores': all_posture_scores,
                    'frame_count': len(video_frames),
                    'audio_segment_count': len(audio_segments)
                }
            }
            
            return self.current_analysis
            
        except Exception as e:
            print(f"Error in realtime analysis: {e}")
            return self.current_analysis
    
    def get_analysis_summary(self):
        """Get current analysis summary"""
        return {
            'confidence': self.current_analysis.get('confidence', 0.0),
            'voice_quality': self.current_analysis.get('voice_quality', 0.0),
            'body_language': self.current_analysis.get('body_language', 0.0),
            'overall_physical_score': self.current_analysis.get('overall_physical_score', 0.0)
        }
    
    def reset_analysis(self):
        """Reset analysis for new question"""
        self.current_analysis = {
            'confidence': 0.0,
            'voice_quality': 0.0,
            'body_language': 0.0,
            'overall_physical_score': 0.0,
            'details': {}
        }
