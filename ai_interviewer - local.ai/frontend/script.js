document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const startBtn = document.getElementById('startBtn');
    const userNameInput = document.getElementById('userName');
    const userExperienceInput = document.getElementById('userExperience');
    const initialSetup = document.getElementById('initial-setup');
    const interviewPanel = document.getElementById('interview-panel');
    const chatbox = document.getElementById('chatbox');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const speechBtn = document.getElementById('speech-btn');
    const status = document.getElementById('status');
    const downloadBtn = document.getElementById('download-report-btn');

    // --- State Variables ---
    let interviewId = null;
    let isAIReplying = false;
    let recognition;

    // --- Speech Recognition & Synthesis Setup ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.lang = 'en-US';
        recognition.interimResults = false;

        recognition.onstart = () => {
            status.textContent = 'Status: Listening...';
            speechBtn.textContent = '🛑';
        };

        recognition.onend = () => {
            status.textContent = 'Status: Idle';
            speechBtn.textContent = '🎤 Speak';
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            userInput.value = transcript;
            sendMessage(); // Automatically send the transcribed text
        };

        recognition.onerror = (event) => {
            status.textContent = `Error: ${event.error}`;
        };

    } else {
        speechBtn.disabled = true;
        status.textContent = 'Status: Speech recognition not supported in this browser.';
    }

    // --- Core Functions ---

    const addMessage = (text, sender) => {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `${sender}-message`);
        messageDiv.textContent = text;
        chatbox.appendChild(messageDiv);
        chatbox.scrollTop = chatbox.scrollHeight; // Scroll to bottom
    };

    const setControlsState = (disabled) => {
        isAIReplying = disabled;
        userInput.disabled = disabled;
        sendBtn.disabled = disabled;
        speechBtn.disabled = disabled;
        status.textContent = disabled ? 'Status: AI is replying...' : 'Status: Idle';
        if (recognition && disabled) {
            recognition.stop();
        }
    };

    const speakText = async (text) => {
        try {
            const response = await fetch('/api/speak', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text }),
            });
            if (!response.ok) throw new Error('Failed to fetch audio.');
            
            const audioBlob = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);
            audio.play();
            
            // Wait for audio to finish before re-enabling controls
            return new Promise(resolve => {
                audio.onended = resolve;
            });

        } catch (error) {
            console.error('Speech synthesis error:', error);
        }
    };
    
    const processAndDisplayAIResponse = async (data) => {
        addMessage(data.response, 'ai');
        await speakText(data.response);
        if (data.interview_over) {
            endInterview(data.final_evaluation);
        }
    };

    const endInterview = async (finalEvaluation) => {
        addMessage(`Interview Over. Final Evaluation: ${finalEvaluation}`, 'ai');
        await speakText(`Interview Over. Final Evaluation: ${finalEvaluation}`);
        setControlsState(true); // Disable all controls permanently
        downloadBtn.style.display = 'block'; // Show download button
    };

    const sendMessage = async () => {
        const userText = userInput.value.trim();
        if (!userText || isAIReplying) return;

        addMessage(userText, 'user');
        userInput.value = '';
        setControlsState(true);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ interview_id: interviewId, text: userText }),
            });
            const data = await response.json();
            await processAndDisplayAIResponse(data);
        } catch (error) {
            console.error('Error sending message:', error);
            addMessage('Sorry, an error occurred. Please try again.', 'ai');
        } finally {
            if (!downloadBtn.style.display || downloadBtn.style.display === 'none') {
                setControlsState(false);
            }
        }
    };

    // --- Event Listeners ---

    startBtn.addEventListener('click', async () => {
        const userName = userNameInput.value.trim();
        const userExperience = userExperienceInput.value.trim();

        if (!userName || !userExperience) {
            alert('Please enter your name and experience.');
            return;
        }

        try {
            const response = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: userName, experience: userExperience }),
            });
            const data = await response.json();

            interviewId = data.interview_id;
            initialSetup.style.display = 'none';
            interviewPanel.style.display = 'block';
            
            setControlsState(true);
            await processAndDisplayAIResponse(data);
            setControlsState(false);
        } catch (error)
        {
            console.error('Error starting interview:', error);
            alert('Could not start interview. Check console for details.');
        }
    });

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    speechBtn.addEventListener('click', () => {
        if (!recognition || isAIReplying) return;
        
        try {
            recognition.start();
        } catch (error) {
            // Catches error if recognition is already running
            recognition.stop();
        }
    });

    downloadBtn.addEventListener('click', () => {
        window.location.href = `/api/report/${interviewId}`;
    });
});
