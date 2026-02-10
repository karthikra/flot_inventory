document.addEventListener('DOMContentLoaded', () => {
    const roomSelect = document.getElementById('room-select');
    const modeVideo = document.getElementById('mode-video');
    const modeImage = document.getElementById('mode-image');
    const videoMode = document.getElementById('video-mode');
    const imageMode = document.getElementById('image-mode');
    const cameraFeed = document.getElementById('camera-feed');
    const recordBtn = document.getElementById('record-btn');
    const imageInput = document.getElementById('image-input');
    const processing = document.getElementById('processing');
    const resultsContainer = document.getElementById('results-container');

    let mediaStream = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let isRecording = false;
    let sessionId = null;

    // Mode toggle
    modeVideo.addEventListener('change', () => {
        videoMode.style.display = 'block';
        imageMode.style.display = 'none';
        initCamera('video');
    });

    modeImage.addEventListener('change', () => {
        videoMode.style.display = 'none';
        imageMode.style.display = 'block';
        stopCamera();
    });

    // Initialize camera
    async function initCamera(mode) {
        try {
            if (mediaStream) stopCamera();
            mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
                audio: true,
            });
            cameraFeed.srcObject = mediaStream;
        } catch (err) {
            console.error('Camera access denied:', err);
            alert('Camera access is needed for capture. Please allow camera permissions.');
        }
    }

    function stopCamera() {
        if (mediaStream) {
            mediaStream.getTracks().forEach(t => t.stop());
            mediaStream = null;
        }
    }

    // Recording
    recordBtn.addEventListener('click', async () => {
        if (!roomSelect.value) {
            alert('Please select a room first.');
            return;
        }

        if (!isRecording) {
            await startRecording();
        } else {
            stopRecording();
        }
    });

    async function startRecording() {
        // Start a capture session
        const formData = new FormData();
        formData.append('room_id', roomSelect.value);
        formData.append('mode', 'video');

        const resp = await fetch('/capture/start', { method: 'POST', body: formData });
        const html = await resp.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const info = doc.querySelector('[data-session-id]');
        sessionId = info?.dataset.sessionId;

        recordedChunks = [];
        const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
            ? 'video/webm;codecs=vp9,opus'
            : MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus')
                ? 'video/webm;codecs=vp8,opus'
                : 'video/webm';

        mediaRecorder = new MediaRecorder(mediaStream, { mimeType });
        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) recordedChunks.push(e.data);
        };
        mediaRecorder.onstop = () => uploadVideo();
        mediaRecorder.start(1000); // 1s chunks
        isRecording = true;
        recordBtn.classList.add('recording');
        const mic = document.getElementById('audio-indicator');
        if (mic) mic.style.display = 'flex';
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        isRecording = false;
        recordBtn.classList.remove('recording');
        const mic = document.getElementById('audio-indicator');
        if (mic) mic.style.display = 'none';
    }

    async function uploadVideo() {
        showProcessing('Uploading video...');

        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const formData = new FormData();
        formData.append('file', blob, 'walkthrough.webm');
        formData.append('session_id', sessionId);
        formData.append('room_id', roomSelect.value);

        // Connect to SSE for progress updates
        const evtSource = new EventSource(`/capture/stream/${sessionId}`);
        evtSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            updateProgress(data);
            if (data.status === 'done' || data.status === 'error') {
                evtSource.close();
            }
        };
        evtSource.onerror = () => evtSource.close();

        try {
            const resp = await fetch('/capture/video', { method: 'POST', body: formData });
            const html = await resp.text();
            hideProcessing();
            resultsContainer.innerHTML = html;
        } catch (err) {
            hideProcessing();
            alert('Upload failed: ' + err.message);
        }
    }

    // Image upload
    imageInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file || !roomSelect.value) {
            if (!roomSelect.value) alert('Please select a room first.');
            return;
        }

        showProcessing('Analyzing image...');

        const formData = new FormData();
        formData.append('file', file);
        formData.append('room_id', roomSelect.value);
        formData.append('session_id', sessionId || '0');

        try {
            const resp = await fetch('/capture/image', { method: 'POST', body: formData });
            const html = await resp.text();
            hideProcessing();
            resultsContainer.innerHTML = html;
        } catch (err) {
            hideProcessing();
            alert('Analysis failed: ' + err.message);
        }
    });

    function showProcessing(msg) {
        processing.style.display = 'block';
        document.getElementById('processing-message').textContent = msg;
        document.getElementById('progress-fill').style.width = '0%';
        document.getElementById('processing-status').textContent = '';
        document.getElementById('items-found').textContent = '';
    }

    function hideProcessing() {
        processing.style.display = 'none';
    }

    function updateProgress(data) {
        if (data.progress !== undefined) {
            document.getElementById('progress-fill').style.width = (data.progress * 100) + '%';
        }
        if (data.message) {
            document.getElementById('processing-status').textContent = data.message;
        }
        if (data.items_found !== undefined) {
            document.getElementById('items-found').textContent = data.items_found + ' items found';
        }
    }

    // Auto-init camera for video mode
    initCamera('video');

    // Expose for mode switch
    window.switchToImageMode = function() {
        modeImage.checked = true;
        modeImage.dispatchEvent(new Event('change'));
    };
});
