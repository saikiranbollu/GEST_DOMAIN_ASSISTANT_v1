/**
 * Generate the HTML content for the webview - Galaxy Theme
 */
export function getWebviewContent(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEST Assistant</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #e0e6f0; background: #0a0e1a;
            min-height: 100vh; overflow-x: hidden; position: relative;
        }
        #galaxy-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none; }
        .container { position: relative; z-index: 1; max-width: 820px; margin: 0 auto; padding: 40px 28px 60px; }

        /* Header */
        .header { text-align: center; margin-bottom: 36px; padding-bottom: 24px; border-bottom: 1px solid rgba(130,160,255,0.15); }
        .header h1 {
            font-size: 28px; font-weight: 700;
            background: linear-gradient(135deg, #7eb4ff 0%, #b07aff 50%, #ff7eb3 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
            letter-spacing: -0.5px; margin-bottom: 6px;
        }
        .header p { font-size: 13px; color: #8892b0; letter-spacing: 0.3px; }

        /* Glass Card */
        .glass-card {
            background: rgba(15,20,40,0.65); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(130,160,255,0.12); border-radius: 16px; padding: 32px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04);
        }

        /* Form */
        .form-group { margin-bottom: 22px; }
        label { display: block; margin-bottom: 8px; font-weight: 500; font-size: 13px; color: #a8b4d0; }
        .label-hint { font-weight: 400; color: #5a6580; font-size: 11px; }
        select, textarea {
            width: 100%; padding: 10px 14px; background: rgba(10,14,30,0.7);
            border: 1px solid rgba(130,160,255,0.18); color: #d0d8f0;
            font-family: inherit; font-size: 13px; border-radius: 10px; transition: all 0.25s ease;
        }
        select:hover, textarea:hover { border-color: rgba(130,160,255,0.35); }
        select:focus, textarea:focus {
            outline: none; border-color: #7e8fff;
            box-shadow: 0 0 0 3px rgba(126,143,255,0.15), 0 0 20px rgba(126,143,255,0.08);
            background: rgba(10,14,30,0.9);
        }
        textarea { resize: vertical; min-height: 100px; font-family: 'Cascadia Code','Fira Code',monospace; font-size: 12px; line-height: 1.6; }
        textarea.notes-input { min-height: 60px; }
        select {
            cursor: pointer; appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%237e8fff' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat; background-position: right 12px center; padding-right: 36px;
        }
        select option { background: #0f1428; color: #d0d8f0; }

        /* Buttons */
        .button-group { margin-top: 28px; }
        .btn-generate {
            width: 100%; padding: 14px 24px; border: none; border-radius: 12px;
            font-family: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
            transition: all 0.3s ease; position: relative; overflow: hidden;
            background: linear-gradient(135deg, #5b6cff 0%, #8b5cf6 50%, #c77dff 100%);
            color: #fff; box-shadow: 0 4px 20px rgba(91,108,255,0.3);
        }
        .btn-generate:hover { transform: translateY(-1px); box-shadow: 0 6px 28px rgba(91,108,255,0.45); }
        .btn-generate:active { transform: translateY(0); }
        .btn-generate:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }
        .btn-generate::after {
            content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
            background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.08) 50%, transparent 70%);
            animation: shimmer 3s infinite;
        }
        @keyframes shimmer { 0% { transform: translateX(-100%) rotate(45deg); } 100% { transform: translateX(100%) rotate(45deg); } }

        /* Action Buttons Row */
        .action-buttons { display: flex; gap: 10px; margin-top: 16px; }
        .btn-action {
            flex: 1; padding: 10px 16px; border: none; border-radius: 10px;
            font-family: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
            transition: all 0.25s ease;
        }
        .btn-accept { background: rgba(34,197,94,0.2); border: 1px solid rgba(34,197,94,0.4); color: #4ade80; }
        .btn-accept:hover { background: rgba(34,197,94,0.35); }
        .btn-reject { background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.4); color: #f87171; }
        .btn-reject:hover { background: rgba(239,68,68,0.35); }
        .btn-regenerate { background: rgba(126,143,255,0.2); border: 1px solid rgba(126,143,255,0.4); color: #93a3ff; }
        .btn-regenerate:hover { background: rgba(126,143,255,0.35); }

        /* Status */
        .status {
            padding: 12px 16px; border-radius: 10px; margin-bottom: 18px;
            font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 10px;
            animation: fadeSlideIn 0.3s ease;
        }
        @keyframes fadeSlideIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
        .status.success { background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.25); color: #4ade80; }
        .status.error { background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.25); color: #f87171; }
        .status.loading { background: rgba(126,143,255,0.1); border: 1px solid rgba(126,143,255,0.2); color: #93a3ff; }
        .spinner {
            display: inline-block; width: 16px; height: 16px;
            border: 2px solid rgba(147,163,255,0.3); border-top-color: #93a3ff;
            border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Timer */
        .timer { font-size: 12px; color: #8892b0; margin-top: 8px; text-align: center; font-variant-numeric: tabular-nums; }
        .timer .time { font-weight: 600; color: #93a3ff; font-size: 14px; }

        /* Result Section */
        .result-section {
            margin-top: 28px; padding: 24px;
            background: rgba(15,20,40,0.5); backdrop-filter: blur(12px);
            border: 1px solid rgba(130,160,255,0.1); border-radius: 14px;
            border-left: 3px solid #7e8fff; animation: fadeSlideIn 0.4s ease;
        }
        .result-section h3 { margin-bottom: 16px; font-size: 15px; font-weight: 600; color: #b0bcf0; }
        .metrics { display: grid; grid-template-columns: repeat(2,1fr); gap: 12px; }
        .metric {
            padding: 14px; background: rgba(10,14,30,0.5);
            border: 1px solid rgba(130,160,255,0.08); border-radius: 10px; transition: border-color 0.2s ease;
        }
        .metric:hover { border-color: rgba(130,160,255,0.25); }
        .metric-label { font-size: 11px; font-weight: 500; color: #5a6580; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
        .metric-value {
            font-size: 22px; font-weight: 700;
            background: linear-gradient(135deg,#7eb4ff,#b07aff);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        }
        .metric-value.small { font-size: 12px; word-break: break-all; }
        .llm-badge {
            margin-top: 14px; padding: 10px 14px;
            background: rgba(139,92,246,0.08); border: 1px solid rgba(139,92,246,0.2);
            border-radius: 8px; font-size: 12px; color: #c4b5fd;
        }
        .llm-badge strong { color: #a78bfa; }
        .file-path {
            margin-top: 12px; padding: 10px 14px;
            background: rgba(10,14,30,0.6); border: 1px solid rgba(130,160,255,0.1);
            border-radius: 8px; font-size: 11px; color: #8892b0;
            font-family: 'Cascadia Code','Fira Code',monospace; word-break: break-all;
        }
        .file-path strong { color: #a8b4d0; }
    </style>
</head>
<body>
    <canvas id="galaxy-canvas"></canvas>
    <div class="container">
        <div class="header">
            <h1>GEST Assistant</h1>
            <p>Generate semantic test code powered by RAG + Knowledge Graph + LLM</p>
        </div>
        <div id="statusContainer"></div>
        <div id="timerContainer"></div>
        <div class="glass-card">
            <div class="form-group">
                <label for="module">Module</label>
                <select id="module"><option value="" disabled selected>Loading modules...</option></select>
            </div>
            <div class="form-group">
                <label for="description">Test Description</label>
                <textarea id="description" placeholder="Describe what you want to test..."></textarea>
            </div>
            <div class="form-group">
                <label for="notes">Additional Notes <span class="label-hint">(optional)</span></label>
                <textarea id="notes" class="notes-input" placeholder="Any additional context or requirements..."></textarea>
            </div>
            <div class="form-group">
                <label for="llmModel">LLM Model</label>
                <select id="llmModel"><option value="" disabled selected>Loading models...</option></select>
            </div>
            <div class="button-group">
                <button class="btn-generate" id="generateBtn">Generate Test</button>
            </div>
        </div>
        <div id="resultContainer"></div>
    </div>

    <script>
        /* ===== Galaxy Particle Animation ===== */
        (function() {
            var canvas = document.getElementById('galaxy-canvas');
            var ctx = canvas.getContext('2d');
            var w, h, particles;
            function resize() { w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight; }
            var colors = [[120,160,255],[150,120,255],[180,100,255],[255,130,180],[100,200,255]];
            function cp() {
                return {
                    x: Math.random()*w, y: Math.random()*h,
                    size: Math.random()*1.8+0.3, sx: (Math.random()-0.5)*0.3, sy: (Math.random()-0.5)*0.3,
                    op: Math.random()*0.6+0.1, ps: Math.random()*0.02+0.005,
                    po: Math.random()*Math.PI*2, c: colors[Math.floor(Math.random()*colors.length)], co: 0
                };
            }
            function init() { resize(); var n = Math.min(Math.floor((w*h)/6000),200); particles = []; for(var i=0;i<n;i++) particles.push(cp()); }
            function dc() {
                var md = 120;
                for(var i=0;i<particles.length;i++) for(var j=i+1;j<particles.length;j++) {
                    var dx=particles[i].x-particles[j].x, dy=particles[i].y-particles[j].y, d=Math.sqrt(dx*dx+dy*dy);
                    if(d<md) { var o=(1-d/md)*0.08; ctx.beginPath(); ctx.moveTo(particles[i].x,particles[i].y); ctx.lineTo(particles[j].x,particles[j].y); ctx.strokeStyle='rgba(130,160,255,'+o+')'; ctx.lineWidth=0.5; ctx.stroke(); }
                }
            }
            var t=0;
            function anim() {
                ctx.clearRect(0,0,w,h);
                var g1=ctx.createRadialGradient(w*0.3,h*0.3,0,w*0.3,h*0.3,w*0.7); g1.addColorStop(0,'rgba(60,40,120,0.04)'); g1.addColorStop(1,'transparent'); ctx.fillStyle=g1; ctx.fillRect(0,0,w,h);
                var g2=ctx.createRadialGradient(w*0.7,h*0.7,0,w*0.7,h*0.7,w*0.5); g2.addColorStop(0,'rgba(40,60,140,0.03)'); g2.addColorStop(1,'transparent'); ctx.fillStyle=g2; ctx.fillRect(0,0,w,h);
                t++;
                for(var k=0;k<particles.length;k++) {
                    var p=particles[k]; p.x+=p.sx; p.y+=p.sy;
                    if(p.x<0)p.x=w; if(p.x>w)p.x=0; if(p.y<0)p.y=h; if(p.y>h)p.y=0;
                    p.co=p.op*(0.6+0.4*Math.sin(t*p.ps+p.po)); var c=p.c;
                    ctx.beginPath(); ctx.arc(p.x,p.y,p.size,0,Math.PI*2);
                    ctx.fillStyle='rgba('+c[0]+','+c[1]+','+c[2]+','+p.co+')'; ctx.fill();
                    if(p.size>1) { ctx.beginPath(); ctx.arc(p.x,p.y,p.size*3,0,Math.PI*2); ctx.fillStyle='rgba('+c[0]+','+c[1]+','+c[2]+','+(p.co*0.08)+')'; ctx.fill(); }
                }
                dc(); requestAnimationFrame(anim);
            }
            window.addEventListener('resize', function() { resize(); }); init(); anim();
        })();

        /* ===== VS Code Communication ===== */
        var vscode = acquireVsCodeApi();
        var generateBtn = document.getElementById('generateBtn');
        var moduleSelect = document.getElementById('module');
        var descriptionInput = document.getElementById('description');
        var notesInput = document.getElementById('notes');
        var llmModelSelect = document.getElementById('llmModel');
        var statusContainer = document.getElementById('statusContainer');
        var timerContainer = document.getElementById('timerContainer');
        var resultContainer = document.getElementById('resultContainer');

        var timerInterval = null;
        var timerStartMs = 0;
        var lastGenerationData = null;

        generateBtn.addEventListener('click', handleGenerate);

        // Note: We DON'T request models/modules here on 'load' event
        // Instead, the extension's pushInitialData() will proactively send them
        // This ensures models are discovered and sent to backend FIRST
        
        function handleGenerate() {
            if (!moduleSelect.value) { showStatus('Please select a module', 'error'); return; }
            var desc = descriptionInput.value.trim();
            if (!desc) { showStatus('Please enter a test description', 'error'); return; }
            
            // MANDATORY: Check if LLM model is selected
            if (!llmModelSelect.value || llmModelSelect.value === '') {
                showStatus('Please select an LLM model', 'error');
                return;
            }
            
            generateBtn.disabled = true;
            resultContainer.innerHTML = '';
            showStatus('Generating test...', 'loading');
            startTimer();
            vscode.postMessage({
                command: 'generateTest',
                data: {
                    module: moduleSelect.value,
                    description: desc,
                    notes: notesInput.value,
                    llmModel: llmModelSelect.value
                }
            });
        }

        function startTimer() {
            timerStartMs = Date.now();
            timerContainer.innerHTML = '<div class="timer">Elapsed: <span class="time" id="timerValue">0.0s</span></div>';
            if (timerInterval) clearInterval(timerInterval);
            timerInterval = setInterval(function() {
                var elapsed = (Date.now() - timerStartMs) / 1000;
                var mins = Math.floor(elapsed / 60);
                var secs = (elapsed % 60).toFixed(1);
                var tv = document.getElementById('timerValue');
                if (tv) tv.textContent = mins > 0 ? mins + 'm ' + secs + 's' : secs + 's';
            }, 100);
        }

        function stopTimer() {
            if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        }

        function showStatus(message, type) {
            statusContainer.innerHTML = '<div class="status ' + type + '">' +
                (type === 'loading' ? '<span class="spinner"></span>' : '') +
                '<span>' + message + '</span></div>';
        }

        window.addEventListener('message', function(event) {
            var msg = event.data;
            switch (msg.command) {
                case 'modelsList': populateModels(msg.models); break;
                case 'modulesList': populateModules(msg.modules); break;
                case 'generationComplete':
                    generateBtn.disabled = false;
                    var actualElapsed = timerStartMs ? (Date.now() - timerStartMs) / 1000 : 0;
                    stopTimer();
                    showGenerationResult(msg.data, actualElapsed);
                    break;
                case 'generationError':
                    generateBtn.disabled = false;
                    stopTimer();
                    timerContainer.innerHTML = '';
                    showStatus('Generation failed: ' + msg.error, 'error');
                    break;
                case 'modelSwitched': showStatus('Switched to ' + (msg.model || ''), 'success'); break;
                case 'llmProgress': showStatus(msg.message || 'Enhancing with LLM...', 'loading'); break;
                case 'error': showStatus(msg.error, 'error'); break;
            }
        });

        function populateModules(modules) {
            moduleSelect.innerHTML = '';
            if (!modules || modules.length === 0) {
                var opt = document.createElement('option');
                opt.value = ''; opt.disabled = true; opt.selected = true;
                opt.textContent = 'No modules available';
                moduleSelect.appendChild(opt); return;
            }
            for (var i = 0; i < modules.length; i++) {
                var opt = document.createElement('option');
                opt.value = modules[i]; opt.textContent = modules[i].toUpperCase();
                if (i === 0) opt.selected = true;
                moduleSelect.appendChild(opt);
            }
        }

        function populateModels(models) {
            if (!models || models.length === 0) {
                llmModelSelect.innerHTML = '<option value="" disabled selected>No models available</option>';
                return;
            }
            llmModelSelect.innerHTML = '';
            var hasSelectedModel = false;
            for (var i = 0; i < models.length; i++) {
                var opt = document.createElement('option');
                opt.value = models[i].name;
                opt.textContent = models[i].name + (models[i].isCurrent ? ' (active)' : '');
                // Select the current model OR the first model
                if (models[i].isCurrent || (!hasSelectedModel && i === 0)) {
                    opt.selected = true;
                    hasSelectedModel = true;
                }
                llmModelSelect.appendChild(opt);
            }
        }

        function showGenerationResult(result, actualElapsedSeconds) {
            lastGenerationData = result;
            // Use ACTUAL elapsed time measured by webview timer (includes LLM round-trip)
            // NOT the backend-only generation_time which excludes LLM call
            var genTime = '';
            if (actualElapsedSeconds && actualElapsedSeconds > 0) {
                var mins = Math.floor(actualElapsedSeconds / 60);
                var secs = (actualElapsedSeconds % 60).toFixed(1);
                genTime = mins > 0 ? mins + 'm ' + secs + 's' : secs + 's';
            } else if (result.generation_time) {
                genTime = result.generation_time.display;
            }
            var filePath = result.output_file || '';
            showStatus('Test generated successfully!' + (genTime ? ' (' + genTime + ')' : ''), 'success');
            timerContainer.innerHTML = '';
            var compliancePercent = (result.compliance_score * 100).toFixed(0);
            resultContainer.innerHTML =
                '<div class="result-section">' +
                    '<h3>Generation Result</h3>' +
                    '<div class="metrics">' +
                        '<div class="metric"><div class="metric-label">Test ID</div><div class="metric-value small">' + result.test_id + '</div></div>' +
                        '<div class="metric"><div class="metric-label">Compliance</div><div class="metric-value">' + compliancePercent + '%</div></div>' +
                        '<div class="metric"><div class="metric-label">Generation Time</div><div class="metric-value small">' + genTime + '</div></div>' +
                        '<div class="metric"><div class="metric-label">LLM Model</div><div class="metric-value small">' + (result.llm_enhancement && result.llm_enhancement.model ? result.llm_enhancement.model : 'N/A') + '</div></div>' +
                    '</div>' +
                    (filePath
                        ? '<div class="file-path"><strong>Full Path:</strong> ' + filePath + '</div>'
                        : '') +
                    '<div class="action-buttons">' +
                        '<button class="btn-action btn-accept" onclick="handleAccept()">&#10003; Accept</button>' +
                        '<button class="btn-action btn-reject" onclick="handleReject()">&#10007; Reject</button>' +
                        '<button class="btn-action btn-regenerate" onclick="handleRegenerate()">&#8634; Regenerate</button>' +
                    '</div>' +
                '</div>';
        }

        function handleAccept() {
            if (lastGenerationData) {
                vscode.postMessage({ command: 'acceptTest', data: lastGenerationData });
                showStatus('Test accepted! File saved at: ' + (lastGenerationData.output_file || 'output/'), 'success');
            }
        }

        function handleReject() {
            resultContainer.innerHTML = '';
            lastGenerationData = null;
            showStatus('Test rejected. You can modify your description and regenerate.', 'error');
        }

        function handleRegenerate() {
            resultContainer.innerHTML = '';
            lastGenerationData = null;
            handleGenerate();
        }
    </script>
</body>
</html>`;
}
