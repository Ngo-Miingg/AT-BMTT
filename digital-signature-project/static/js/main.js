// file: static/js/main.js (Phiên bản cuối cùng, tích hợp chế độ thử nghiệm)

document.addEventListener('DOMContentLoaded', function () {
    // =======================================================
    // KHU VỰC ĐIỀU KHIỂN THỬ NGHIỆM
    // =======================================================
    const TEST_MODE = {
        // Đặt là true để bật chế độ thử nghiệm, false để chạy bình thường
        ENABLED: true, 
        
        // Chọn loại lỗi muốn thử: 'signature', 'hash', hoặc 'none'
        // 'signature': Cố tình làm sai chữ ký.
        // 'hash': Cố tình làm sai nội dung (ciphertext) để hash không khớp.
        // 'none': Chạy thử nghiệm nhưng không làm sai dữ liệu.
        CORRUPT: 'none'
    };
    // =======================================================


    const currentUser = document.body.dataset.username;
    if (!currentUser) return; 

    const socket = io();

    // --- BIẾN TRẠNG THÁI ---
    let receivedData = {};
    let verifiedStatus = [];
    let selectedPackageIndex = -1;
    let chatPartner = null;

    // --- LẤY CÁC PHẦN TỬ HTML ---
    const packagesList = document.getElementById('packages-list');
    const detailSection = document.getElementById('details-section');
    const logArea = document.getElementById('log-area');
    const combineButton = document.getElementById('combine-btn');
    const fileInput = document.getElementById('fileInput');
    const sendFileButton = document.getElementById('sendFileBtn');
    const recipientSelect = document.getElementById('recipientSelect');
    const chatWindow = document.getElementById('chat-window');
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const chatPartnerName = document.getElementById('chat-partner-name');
    
    // --- HÀM TIỆN ÍCH ---
    function log(message) {
        logArea.value += `[${new Date().toLocaleTimeString()}] ${message}\n`;
        logArea.scrollTop = logArea.scrollHeight;
    }

    function addChatMessage(sender, message, isMe) {
        const messageWrapper = document.createElement('div');
        messageWrapper.className = `d-flex flex-column mb-2 ${isMe ? 'align-items-end' : 'align-items-start'}`;
        const messageBubble = document.createElement('div');
        messageBubble.className = `p-2 rounded ${isMe ? 'bg-primary' : 'bg-secondary'}`;
        messageBubble.innerHTML = `<strong>${sender}:</strong> ${message}`;
        messageWrapper.appendChild(messageBubble);
        chatWindow.appendChild(messageWrapper);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    // --- HÀM GỌI API & XỬ LÝ LOGIC ---
    async function fetchAPI(url, payload) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (response.status === 401) {
                log("LỖI: Phiên đăng nhập đã hết hạn. Đang chuyển hướng...");
                alert("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
                window.location.href = '/login';
                return null;
            }
            const contentType = response.headers.get("content-type");
            if (!contentType || !contentType.includes("application/json")) {
                throw new Error("Server không trả về dữ liệu JSON. Có thể URL API bị sai.");
            }
            const result = await response.json();
            if (!response.ok) { throw new Error(result.error || 'Lỗi không xác định'); }
            return result;
        } catch (error) {
            log(`LỖI: ${error.message}`);
            return null;
        }
    }
    async function sendFile() {
        if (!fileInput.files.length) { alert('Vui lòng chọn file!'); return; }
        const recipient = recipientSelect.value;
        if (!recipient) { alert('Vui lòng chọn người nhận!'); return; }
        const file = fileInput.files[0];
        const formData = new FormData();
        formData.append('file', file);
        formData.append('recipient', recipient);
        log(`Đang mã hóa và gửi file tới ${recipient}...`);
        try {
            const response = await fetch('/api/send', { method: 'POST', body: formData });
            const result = await response.json();
            if (result.success) {
                log(`-> Gửi thành công!`);
                socket.emit('chat_message', { recipient: recipient, message: 'Hello!' });
                addChatMessage(currentUser, 'Hello!', true);
                chatPartner = recipient;
                chatPartnerName.textContent = chatPartner;
            } else { log(`-> Lỗi: ${result.error}`); }
        } catch(error) { log(`Lỗi mạng: ${error}`); }
    }
    
    async function handleVerification(type) {
        const currentSelection = document.querySelector('#packages-list .list-group-item.active');
        if (!currentSelection) { alert('Vui lòng chọn một gói tin từ danh sách!'); return; }
        
        selectedPackageIndex = parseInt(currentSelection.dataset.index);
        // Tạo một bản copy của gói tin để không làm thay đổi dữ liệu gốc
        const pkg = JSON.parse(JSON.stringify(receivedData.packages[selectedPackageIndex]));
        
        // Logic của chế độ thử nghiệm
        if (TEST_MODE.ENABLED) {
            if (type === 'signature' && TEST_MODE.CORRUPT === 'signature') {
                log(">>> THỬ NGHIỆM: Cố tình làm sai Chữ ký <<<");
                pkg.sig = "tampered==" + pkg.sig.substring(10);
            }
            if (type === 'hash' && TEST_MODE.CORRUPT === 'hash') {
                log(">>> THỬ NGHIỆM: Cố tình làm sai Ciphertext <<<");
                pkg.cipher = "tampered==" + pkg.cipher.substring(10);
            }
        }
        
        let url;
        if (type === 'decrypt') {
             // Nút giải mã giờ chỉ để đánh dấu là sẵn sàng
             log(`[P${selectedPackageIndex + 1}] Đã xác thực xong. Sẵn sàng để lắp ráp.`);
             verifiedStatus[selectedPackageIndex] = true;
             renderPackagesList();
             checkAllVerified();
             return;
        } else {
             url = `/api/verify/${type}`;
        }

        let payload = { package: pkg };
        if(type === 'signature') payload.sender = receivedData.sender;
        
        log(`[P${selectedPackageIndex + 1}] Yêu cầu ${type}...`);
        const result = await fetchAPI(url, payload);
        
        if (result) {
            log(`-> Kết quả: ${result.valid ? 'HỢP LỆ' : 'KHÔNG HỢP LỆ'}`);
            if(!result.valid) {
                const reason = (type === 'signature') 
                    ? `Chữ ký không hợp lệ ở [Phần ${selectedPackageIndex + 1}]`
                    : `Hash không trùng khớp ở [Phần ${selectedPackageIndex + 1}]`;
                socket.emit('send_nack', { recipient: receivedData.sender, reason: reason });
                alert(`PHÁT HIỆN LỖI TOÀN VẸN! Đã gửi cảnh báo (NACK) tới ${receivedData.sender}.`);
            }
        }
    }

    // Các hàm render, display, check giữ nguyên...
    function renderPackagesList() {
        packagesList.innerHTML = '';
        if (!receivedData.packages || receivedData.packages.length === 0) {
            packagesList.innerHTML = '<p class="text-muted">Không có gói tin nào.</p>';
            detailSection.style.display = 'none';
            return;
        }
        detailSection.style.display = 'block';
        receivedData.packages.forEach((pkg, index) => {
            const listItem = document.createElement('a');
            listItem.href = "#";
            listItem.dataset.index = index;
            listItem.className = `list-group-item list-group-item-action ${selectedPackageIndex === index ? 'active' : ''}`;
            let statusBadge = verifiedStatus[index] ? `<span class="badge bg-success float-end"><i class="bi bi-check-circle-fill"></i> Sẵn sàng</span>` : `<span class="badge bg-secondary float-end">Đang chờ</span>`;
            listItem.innerHTML = `Gói tin Phần ${index + 1} <small class="text-muted d-block">Từ: ${receivedData.sender}</small> ${statusBadge}`;
            listItem.addEventListener('click', (e) => { e.preventDefault(); displayPackageDetails(index); });
            packagesList.appendChild(listItem);
        });
    }

    function displayPackageDetails(index) {
        selectedPackageIndex = index;
        const pkg = receivedData.packages[index];
        detailSection.style.display = 'block';
        detailSection.querySelector('h6').innerHTML = `<i class="bi bi-info-circle-fill"></i> Chi Tiết Gói Tin (Phần ${index + 1})`;
        document.getElementById('detail-iv').value = pkg.iv;
        document.getElementById('detail-hash').value = pkg.hash;
        document.getElementById('detail-sig').value = pkg.sig;
        renderPackagesList();
    }
    
    function checkAllVerified() {
        if (!verifiedStatus) return;
        const allDone = verifiedStatus.every(status => status === true);
        if (allDone) {
            log(">>> TUYỆT VỜI! Tất cả các phần đã hợp lệ. Bạn có thể ghép và tải file.");
            combineButton.disabled = false;
        }
    }


    // --- LẮNG NGHE SỰ KIỆN VÀ KHỞI TẠO ---
    socket.on('connect', () => { log('Đã kết nối tới server real-time.'); });
    socket.on('disconnect', () => { log('Mất kết nối tới server real-time.'); });
    socket.on('nack_received', (data) => {
        const errorMessage = `!!! CẢNH BÁO TỪ ${data.from} !!!\n\nLý do: ${data.reason}`;
        log(errorMessage);
        alert(errorMessage);
    });
    socket.on('receive_file', (data) => {
        log(`Đã nhận chi tiết file "${data.original_filename}" từ ${data.sender}.`);
        receivedData = data;
        verifiedStatus = new Array(data.packages.length).fill(false);
        selectedPackageIndex = -1;
        combineButton.disabled = true;
        renderPackagesList();
        alert(`Bạn có file mới từ ${data.sender}!`);
        chatPartner = data.sender;
        chatPartnerName.textContent = chatPartner;
        socket.emit('chat_message', { recipient: chatPartner, message: 'Ready!' });
        addChatMessage(currentUser, 'Ready!', true);
    });

    socket.on('new_chat_message', (data) => {
        addChatMessage(data.sender, data.message, false);
        if (!chatPartner || chatPartner !== data.sender) {
             chatPartner = data.sender;
             chatPartnerName.textContent = chatPartner;
        }
    });

    combineButton.addEventListener('click', async () => {
        log("Đang yêu cầu server lắp ráp file...");
        const payload = {
            encrypted_session_key: receivedData.encrypted_session_key,
            packages: receivedData.packages,
            original_filename: receivedData.original_filename
        };
        const result = await fetchAPI('/api/assemble', payload);
        if (result && result.success) {
            log(`Server đã lắp ráp file thành công. Bắt đầu tải về...`);
            const link = document.createElement('a');
            link.href = `/download/${result.download_token}`;
            link.setAttribute('download', result.original_filename);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } else { log("Lỗi khi lắp ráp file trên server."); }
    });
    
    function sendMessage() {
        const message = chatInput.value.trim();
        if (message && chatPartner) {
            socket.emit('chat_message', { recipient: chatPartner, message: message });
            addChatMessage(currentUser, message, true);
            chatInput.value = '';
        } else if (!chatPartner) {
            alert("Vui lòng gửi/nhận một file hoặc tin nhắn để bắt đầu cuộc trò chuyện!");
        }
    }
    chatSendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { sendMessage(); } });
    sendFileButton.addEventListener('click', sendFile);
    document.getElementById('verify-sig-btn').addEventListener('click', () => handleVerification('signature'));
    document.getElementById('verify-hash-btn').addEventListener('click', () => handleVerification('hash'));
    document.getElementById('decrypt-btn').addEventListener('click', () => handleVerification('decrypt'));
    
    log('Hệ thống sẵn sàng.');
});