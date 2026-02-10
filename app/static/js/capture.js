document.addEventListener('DOMContentLoaded', () => {
    const roomSelect = document.getElementById('room-select');
    const modeVideo = document.getElementById('mode-video');
    const modeImage = document.getElementById('mode-image');
    const modeRapid = document.getElementById('mode-rapid');
    const videoMode = document.getElementById('video-mode');
    const imageMode = document.getElementById('image-mode');
    const rapidMode = document.getElementById('rapid-mode');
    const cameraFeed = document.getElementById('camera-feed');
    const recordBtn = document.getElementById('record-btn');
    const imageInput = document.getElementById('image-input');
    const processing = document.getElementById('processing');
    const resultsContainer = document.getElementById('results-container');

    const detectBtn = document.getElementById('detect-btn');
    const detectionOverlay = document.getElementById('detection-overlay');
    const overlayCtx = detectionOverlay.getContext('2d');

    // Rapid capture elements
    const rapidCameraFeed = document.getElementById('rapid-camera-feed');
    const snapBtn = document.getElementById('snap-btn');
    const rapidDoneBtn = document.getElementById('rapid-done-btn');
    const snapCounter = document.getElementById('snap-counter');
    const snapStrip = document.getElementById('snap-strip');

    let mediaStream = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let isRecording = false;
    let sessionId = null;
    let detectClearTimer = null;

    // Rapid capture state
    let rapidStream = null;
    let rapidSnaps = [];         // { blob, timestamp }
    let rapidAudioRecorder = null;
    let rapidAudioChunks = [];
    let rapidStartTime = null;

    // Mode toggle
    modeVideo.addEventListener('change', () => {
        videoMode.style.display = 'block';
        imageMode.style.display = 'none';
        rapidMode.style.display = 'none';
        stopRapidCamera();
        initCamera('video');
    });

    modeImage.addEventListener('change', () => {
        videoMode.style.display = 'none';
        imageMode.style.display = 'block';
        rapidMode.style.display = 'none';
        stopCamera();
        stopRapidCamera();
    });

    modeRapid.addEventListener('change', () => {
        videoMode.style.display = 'none';
        imageMode.style.display = 'none';
        rapidMode.style.display = 'block';
        stopCamera();
        initRapidCamera();
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

    // --- Rapid Capture ---
    async function initRapidCamera() {
        if (!roomSelect.value) {
            alert('Please select a room first.');
            modeVideo.checked = true;
            modeVideo.dispatchEvent(new Event('change'));
            return;
        }

        try {
            if (rapidStream) stopRapidCamera();
            rapidStream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
                audio: true,
            });
            rapidCameraFeed.srcObject = rapidStream;

            // Start a capture session
            const formData = new FormData();
            formData.append('room_id', roomSelect.value);
            formData.append('mode', 'rapid');

            const resp = await fetch('/capture/start', { method: 'POST', body: formData });
            const html = await resp.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const info = doc.querySelector('[data-session-id]');
            sessionId = info?.dataset.sessionId;

            // Start audio recording
            rapidSnaps = [];
            rapidAudioChunks = [];
            rapidStartTime = Date.now();
            updateSnapCounter();
            snapStrip.innerHTML = '';
            rapidDoneBtn.style.display = 'none';

            // Try audio-only recording from the stream
            const audioTrack = rapidStream.getAudioTracks()[0];
            if (audioTrack) {
                const audioStream = new MediaStream([audioTrack]);
                const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                    ? 'audio/webm;codecs=opus'
                    : MediaRecorder.isTypeSupported('audio/mp4')
                        ? 'audio/mp4'
                        : '';

                if (mimeType) {
                    rapidAudioRecorder = new MediaRecorder(audioStream, { mimeType });
                    rapidAudioRecorder.ondataavailable = (e) => {
                        if (e.data.size > 0) rapidAudioChunks.push(e.data);
                    };
                    rapidAudioRecorder.start(1000);

                    const mic = document.getElementById('rapid-audio-indicator');
                    if (mic) mic.style.display = 'flex';
                }
            }
        } catch (err) {
            console.error('Rapid camera access denied:', err);
            alert('Camera access is needed for rapid capture. Please allow camera permissions.');
        }
    }

    function stopRapidCamera() {
        if (rapidAudioRecorder && rapidAudioRecorder.state !== 'inactive') {
            rapidAudioRecorder.stop();
        }
        rapidAudioRecorder = null;
        if (rapidStream) {
            rapidStream.getTracks().forEach(t => t.stop());
            rapidStream = null;
        }
        const mic = document.getElementById('rapid-audio-indicator');
        if (mic) mic.style.display = 'none';
    }

    // Snap handler
    snapBtn.addEventListener('click', () => {
        if (!rapidStream) return;

        const canvas = document.createElement('canvas');
        canvas.width = rapidCameraFeed.videoWidth;
        canvas.height = rapidCameraFeed.videoHeight;
        canvas.getContext('2d').drawImage(rapidCameraFeed, 0, 0);

        canvas.toBlob((blob) => {
            if (!blob) return;
            const timestamp = (Date.now() - rapidStartTime) / 1000;
            rapidSnaps.push({ blob, timestamp });
            updateSnapCounter();
            addSnapThumbnail(canvas, rapidSnaps.length);

            if (rapidSnaps.length >= 1) {
                rapidDoneBtn.style.display = 'inline-flex';
            }

            // Visual feedback: brief scale animation
            snapBtn.classList.add('snap-flash');
            setTimeout(() => snapBtn.classList.remove('snap-flash'), 150);
        }, 'image/jpeg', 0.92);
    });

    function updateSnapCounter() {
        const n = rapidSnaps.length;
        snapCounter.textContent = n === 1 ? '1 photo' : `${n} photos`;
    }

    function addSnapThumbnail(canvas, num) {
        const thumb = document.createElement('div');
        thumb.className = 'snap-thumb';

        const img = document.createElement('img');
        img.src = canvas.toDataURL('image/jpeg', 0.4);
        thumb.appendChild(img);

        const badge = document.createElement('span');
        badge.className = 'snap-thumb-badge';
        badge.textContent = num;
        thumb.appendChild(badge);

        snapStrip.appendChild(thumb);
        snapStrip.scrollLeft = snapStrip.scrollWidth;
    }

    // Done handler
    rapidDoneBtn.addEventListener('click', async () => {
        if (rapidSnaps.length === 0) return;

        // Stop audio recording and wait for final data
        let audioBlob = null;
        if (rapidAudioRecorder && rapidAudioRecorder.state !== 'inactive') {
            await new Promise(resolve => {
                rapidAudioRecorder.onstop = resolve;
                rapidAudioRecorder.stop();
            });
            if (rapidAudioChunks.length > 0) {
                audioBlob = new Blob(rapidAudioChunks, { type: rapidAudioChunks[0].type || 'audio/webm' });
            }
        }

        stopRapidCamera();
        showProcessing(`Analyzing ${rapidSnaps.length} snapshots...`);

        const formData = new FormData();
        formData.append('session_id', sessionId);
        formData.append('room_id', roomSelect.value);

        // Append each snap image
        for (let i = 0; i < rapidSnaps.length; i++) {
            formData.append(`snaps[${i}]`, rapidSnaps[i].blob, `snap_${i}.jpg`);
        }

        // Timestamps as JSON
        const timestamps = rapidSnaps.map(s => s.timestamp);
        formData.append('timestamps', JSON.stringify(timestamps));

        // Optional audio
        if (audioBlob) {
            formData.append('audio', audioBlob, 'rapid_audio.webm');
        }

        // Connect to SSE for progress
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
            const resp = await fetch('/capture/rapid', { method: 'POST', body: formData });
            const html = await resp.text();
            hideProcessing();
            resultsContainer.innerHTML = html;
        } catch (err) {
            hideProcessing();
            alert('Analysis failed: ' + err.message);
        }
    });

    // --- Recording (Video mode) ---
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

    // --- Live Detection ---
    detectBtn.addEventListener('click', async () => {
        if (!roomSelect.value) {
            alert('Please select a room first.');
            return;
        }
        if (detectBtn.classList.contains('detecting')) return;

        detectBtn.classList.add('detecting');
        detectBtn.querySelector('span').textContent = 'Detecting...';

        try {
            // Capture frame from live video
            const snapCanvas = document.createElement('canvas');
            snapCanvas.width = cameraFeed.videoWidth;
            snapCanvas.height = cameraFeed.videoHeight;
            snapCanvas.getContext('2d').drawImage(cameraFeed, 0, 0);

            const blob = await new Promise(resolve =>
                snapCanvas.toBlob(resolve, 'image/jpeg', 0.85)
            );

            const formData = new FormData();
            formData.append('file', blob, 'frame.jpg');

            const resp = await fetch('/capture/detect', { method: 'POST', body: formData });
            if (!resp.ok) throw new Error('Detection failed');
            const objects = await resp.json();

            drawDetections(objects);
        } catch (err) {
            console.error('Detection error:', err);
        } finally {
            detectBtn.classList.remove('detecting');
            detectBtn.querySelector('span').textContent = 'Detect';
        }
    });

    function drawDetections(objects) {
        // Size canvas to match the video element's display size
        const rect = cameraFeed.getBoundingClientRect();
        detectionOverlay.width = rect.width * devicePixelRatio;
        detectionOverlay.height = rect.height * devicePixelRatio;
        overlayCtx.scale(devicePixelRatio, devicePixelRatio);

        const w = rect.width;
        const h = rect.height;

        overlayCtx.clearRect(0, 0, w, h);

        for (const obj of objects) {
            if (!obj.bounding_box || obj.bounding_box.length < 4) continue;

            const [x1, y1, x2, y2] = obj.bounding_box;
            const bx = x1 * w;
            const by = y1 * h;
            const bw = (x2 - x1) * w;
            const bh = (y2 - y1) * h;

            // Box
            overlayCtx.strokeStyle = '#00e5ff';
            overlayCtx.lineWidth = 2;
            overlayCtx.strokeRect(bx, by, bw, bh);

            // Label background
            const label = `${obj.name} ${Math.round(obj.confidence * 100)}%`;
            overlayCtx.font = '600 13px system-ui, sans-serif';
            const textMetrics = overlayCtx.measureText(label);
            const labelH = 20;
            const labelW = textMetrics.width + 10;
            const labelY = by > labelH ? by - labelH : by;

            overlayCtx.fillStyle = 'rgba(0, 229, 255, 0.85)';
            overlayCtx.fillRect(bx, labelY, labelW, labelH);

            // Label text
            overlayCtx.fillStyle = '#000';
            overlayCtx.fillText(label, bx + 5, labelY + 14);
        }

        // Auto-clear after 8 seconds
        if (detectClearTimer) clearTimeout(detectClearTimer);
        detectClearTimer = setTimeout(() => {
            overlayCtx.clearRect(0, 0, detectionOverlay.width, detectionOverlay.height);
        }, 8000);
    }

    // Auto-init camera for video mode
    initCamera('video');

    // Expose for mode switch
    window.switchToImageMode = function() {
        modeImage.checked = true;
        modeImage.dispatchEvent(new Event('change'));
    };
});
