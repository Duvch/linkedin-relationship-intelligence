document.addEventListener('DOMContentLoaded', () => {
    loadUserInfo();
    loadProfiles();
    loadPosts();
    loadEmailSettings();
    loadLinkedInSettings();
    loadNotifications();
    updateNotifBadge();

    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab).classList.add('active');
            if (tab.dataset.tab === 'notifications') loadNotifications();
        });
    });
});

async function loadUserInfo() {
    try {
        const res = await fetch('/api/me');
        if (res.status === 401) {
            window.location.href = '/';
            return;
        }
        const user = await res.json();
        const greeting = document.getElementById('user-greeting');
        if (greeting) greeting.textContent = `Hi, ${user.display_name}`;
    } catch (err) {}
}

async function loadProfiles() {
    const container = document.getElementById('profiles-list');
    try {
        const res = await fetch('/profiles');
        const profiles = await res.json();

        if (profiles.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="grid-column: 1/-1">
                    <h3>No profiles yet</h3>
                    <p>Click "+ Add Profile" to start tracking LinkedIn profiles.</p>
                </div>`;
            return;
        }

        container.innerHTML = profiles.map(p => `
            <div class="profile-card">
                <div class="profile-card-header">
                    <div class="profile-name">${escapeHtml(p.name)}</div>
                    <span class="profile-type ${p.type}">${p.type}</span>
                </div>
                <a href="${escapeHtml(p.linkedin_url)}" target="_blank" class="profile-url">${escapeHtml(p.linkedin_url)}</a>
                <div class="profile-meta">
                    <span>Added ${formatDate(p.created_at)}</span>
                    <button class="btn btn-danger" onclick="deleteProfile(${p.id}, '${escapeHtml(p.name)}')">Delete</button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = '<p class="loading">Failed to load profiles.</p>';
    }
}

async function loadPosts() {
    const container = document.getElementById('posts-list');
    try {
        const res = await fetch('/posts?limit=50');
        const posts = await res.json();

        if (posts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>No posts yet</h3>
                    <p>Posts will appear here after the daily job runs or you trigger it manually.</p>
                </div>`;
            return;
        }

        const profileRes = await fetch('/profiles');
        const profiles = await profileRes.json();
        const profileMap = {};
        profiles.forEach(p => { profileMap[p.id] = p; });

        const grouped = {};
        posts.forEach(post => {
            const dateStr = formatDayGroup(post.post_timestamp || post.created_at);
            if (!grouped[dateStr]) grouped[dateStr] = [];
            grouped[dateStr].push(post);
        });

        let html = '';
        for (const [day, dayPosts] of Object.entries(grouped)) {
            html += `<div class="day-group">`;
            html += `<div class="day-header">${escapeHtml(day)}</div>`;
            html += dayPosts.map(post => {
                const profile = profileMap[post.profile_id] || {};
                const profileName = profile.name || 'Unknown';
                const profileUrl = profile.linkedin_url || '';
                const categoryClass = (post.category || 'other').toLowerCase().replace(/\s+/g, '-');
                return `
                <div class="post-card">
                    <div class="post-card-header">
                        <div class="post-author-info">
                            <span class="post-author-avatar">${profileName.charAt(0).toUpperCase()}</span>
                            <div>
                                <span class="post-author">${profileUrl ? `<a href="${escapeHtml(profileUrl)}" target="_blank" class="author-link">${escapeHtml(profileName)}</a>` : escapeHtml(profileName)}</span>
                                <span class="post-time">${formatTimeAgo(post.post_timestamp || post.created_at)}</span>
                            </div>
                        </div>
                        <span class="post-category ${categoryClass}">${escapeHtml(post.category || 'Other')}</span>
                    </div>
                    <div class="post-summary">${escapeHtml(post.summary || 'No summary')}</div>
                    <div class="post-text-preview">${escapeHtml(truncate(post.post_text, 200))}</div>
                    <div class="post-reply">
                        <div class="post-reply-label">Suggested Reply</div>
                        ${escapeHtml(post.suggested_reply || 'N/A')}
                    </div>
                    <div class="post-footer">
                        ${post.post_url ? `<a href="${escapeHtml(post.post_url)}" target="_blank" class="view-post-link">View on LinkedIn</a>` : ''}
                    </div>
                </div>`;
            }).join('');
            html += `</div>`;
        }

        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '<p class="loading">Failed to load posts.</p>';
    }
}

async function loadNotifications() {
    const container = document.getElementById('notifications-list');
    try {
        const res = await fetch('/notifications?limit=50');
        const notifs = await res.json();

        if (notifs.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>No notifications yet</h3>
                    <p>Notifications will appear here after the daily job runs.</p>
                </div>`;
            return;
        }

        const grouped = {};
        notifs.forEach(n => {
            const dateStr = formatDayGroup(n.created_at);
            if (!grouped[dateStr]) grouped[dateStr] = [];
            grouped[dateStr].push(n);
        });

        let html = '';
        for (const [day, dayNotifs] of Object.entries(grouped)) {
            html += `<div class="day-group">`;
            html += `<div class="day-header">${escapeHtml(day)}</div>`;
            html += dayNotifs.map(n => `
                <div class="notif-card ${n.is_read ? 'read' : 'unread'}">
                    <div class="notif-header">
                        <span class="notif-title">${escapeHtml(n.title)}</span>
                        <span class="notif-time">${formatTimeAgo(n.created_at)}</span>
                    </div>
                    <div class="notif-body">${formatNotifBody(n.body)}</div>
                    ${!n.is_read ? `<button class="btn btn-secondary notif-read-btn" onclick="markRead(${n.id})">Mark Read</button>` : ''}
                </div>
            `).join('');
            html += `</div>`;
        }

        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '<p class="loading">Failed to load notifications.</p>';
    }
}

async function updateNotifBadge() {
    try {
        const res = await fetch('/notifications/unread-count');
        const data = await res.json();
        const badge = document.getElementById('notif-badge');
        if (data.count > 0) {
            badge.textContent = data.count;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    } catch (err) {}
}

async function markRead(id) {
    await fetch(`/notifications/mark-read/${id}`, { method: 'POST' });
    loadNotifications();
    updateNotifBadge();
}

async function markAllRead() {
    await fetch('/notifications/mark-all-read', { method: 'POST' });
    loadNotifications();
    updateNotifBadge();
    showToast('All notifications marked as read', 'success');
}

function showAddProfileModal() {
    document.getElementById('modal-overlay').classList.add('active');
}

function showCsvUploadModal() {
    document.getElementById('csv-modal-overlay').classList.add('active');
    document.getElementById('csv-upload-status').textContent = '';
    document.getElementById('csv-upload-status').className = 'status-msg';
}

function closeCsvModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('csv-modal-overlay').classList.remove('active');
    document.getElementById('csv-upload-form').reset();
    document.getElementById('csv-upload-status').textContent = '';
    document.getElementById('csv-upload-status').className = 'status-msg';
}

async function uploadCsv(event) {
    event.preventDefault();
    const fileInput = document.getElementById('csv_file');
    const btn = document.getElementById('csv-upload-btn');
    const status = document.getElementById('csv-upload-status');

    if (!fileInput.files.length) {
        showToast('Please select a CSV file', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    btn.disabled = true;
    btn.textContent = 'Uploading...';
    status.className = 'status-msg loading';
    status.textContent = 'Processing CSV file...';

    try {
        const res = await fetch('/profiles/upload-csv', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        if (res.ok) {
            status.className = 'status-msg success';
            status.textContent = data.message;
            if (data.errors && data.errors.length > 0) {
                status.textContent += ' Errors: ' + data.errors.join('; ');
            }
            showToast(`Imported ${data.added} profile(s)`, 'success');
            loadProfiles();
            setTimeout(() => closeCsvModal(), 2000);
        } else {
            status.className = 'status-msg error';
            status.textContent = data.detail || 'Upload failed';
            showToast(data.detail || 'CSV upload failed', 'error');
        }
    } catch (err) {
        status.className = 'status-msg error';
        status.textContent = 'Failed to upload CSV';
        showToast('Failed to upload CSV', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Upload & Import';
    }
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('modal-overlay').classList.remove('active');
    document.getElementById('add-profile-form').reset();
}

async function addProfile(event) {
    event.preventDefault();
    const data = {
        name: document.getElementById('name').value,
        linkedin_url: document.getElementById('linkedin_url').value,
    };

    try {
        const res = await fetch('/profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });

        if (!res.ok) {
            const err = await res.json();
            showToast(err.detail || 'Failed to add profile', 'error');
            return;
        }

        closeModal();
        showToast('Profile added successfully', 'success');
        loadProfiles();
    } catch (err) {
        showToast('Failed to add profile', 'error');
    }
}

async function deleteProfile(id, name) {
    if (!confirm(`Delete profile "${name}"? This will also remove all their posts.`)) return;

    try {
        const res = await fetch(`/profiles/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showToast('Profile deleted', 'success');
            loadProfiles();
            loadPosts();
        } else {
            showToast('Failed to delete profile', 'error');
        }
    } catch (err) {
        showToast('Failed to delete profile', 'error');
    }
}

async function triggerJob() {
    const btn = document.getElementById('trigger-btn');
    const status = document.getElementById('job-status');
    btn.disabled = true;
    btn.textContent = 'Running...';
    status.className = 'status-msg loading';
    status.textContent = 'Job is running, this may take a moment...';

    try {
        const res = await fetch('/trigger-job', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            status.className = 'status-msg success';
            status.textContent = data.message;
            loadPosts();
            loadNotifications();
            updateNotifBadge();
        } else {
            status.className = 'status-msg error';
            status.textContent = data.detail || 'Job failed';
        }
    } catch (err) {
        status.className = 'status-msg error';
        status.textContent = 'Failed to trigger job';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Daily Job';
    }
}

async function checkHealth() {
    const status = document.getElementById('health-status');
    status.className = 'status-msg loading';
    status.textContent = 'Checking...';

    try {
        const res = await fetch('/health');
        const data = await res.json();
        status.className = 'status-msg success';
        status.textContent = `Status: ${data.status}`;
    } catch (err) {
        status.className = 'status-msg error';
        status.textContent = 'Health check failed';
    }
}

async function loadEmailSettings() {
    try {
        const res = await fetch('/settings/email');
        const settings = await res.json();
        if (settings.notify_email) document.getElementById('notify_email').value = settings.notify_email;
        if (settings.smtp_user) document.getElementById('smtp_user').value = settings.smtp_user;
        if (settings.smtp_host) document.getElementById('smtp_host').value = settings.smtp_host;
        if (settings.smtp_port) document.getElementById('smtp_port').value = settings.smtp_port;
        if (settings.smtp_password && settings.smtp_password !== '') {
            document.getElementById('smtp_password').placeholder = 'Password saved (enter new to change)';
        }
    } catch (err) {
        console.log('Could not load email settings');
    }
}

async function saveEmailSettings(event) {
    event.preventDefault();
    const status = document.getElementById('email-status');

    const data = {
        notify_email: document.getElementById('notify_email').value,
        smtp_user: document.getElementById('smtp_user').value,
        smtp_host: document.getElementById('smtp_host').value,
        smtp_port: document.getElementById('smtp_port').value,
        smtp_password: document.getElementById('smtp_password').value,
    };

    status.className = 'status-msg loading';
    status.textContent = 'Saving...';

    try {
        const res = await fetch('/settings/email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (res.ok) {
            status.className = 'status-msg success';
            status.textContent = 'Email settings saved!';
            showToast('Email settings saved', 'success');
            document.getElementById('smtp_password').value = '';
            document.getElementById('smtp_password').placeholder = 'Password saved (enter new to change)';
        } else {
            const err = await res.json();
            status.className = 'status-msg error';
            status.textContent = err.detail || 'Failed to save';
        }
    } catch (err) {
        status.className = 'status-msg error';
        status.textContent = 'Failed to save settings';
    }
}

async function loadLinkedInSettings() {
    try {
        const res = await fetch('/settings/linkedin');
        const settings = await res.json();
        const statusEl = document.getElementById('linkedin-status');
        if (settings.linkedin_configured) {
            statusEl.className = 'status-msg success';
            statusEl.textContent = 'RapidAPI key configured - ready to fetch posts';
        } else {
            statusEl.className = 'status-msg error';
            statusEl.textContent = 'RapidAPI key not found. Add RAPIDAPI_KEY to your environment secrets.';
        }
    } catch (err) {
        console.log('Could not load LinkedIn settings');
    }
}

function showToast(message, type) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    setTimeout(() => { toast.classList.remove('show'); }, 3000);
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDayGroup(dateStr) {
    if (!dateStr) return 'Unknown Date';
    const d = new Date(dateStr);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const postDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.floor((today - postDay) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return d.toLocaleDateString('en-US', { weekday: 'long' });
    return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

function formatTimeAgo(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHrs = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHrs < 24) return `${diffHrs}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatNotifBody(body) {
    if (!body) return '';
    return escapeHtml(body).split('\n').map(line => {
        const parts = line.split(/(https?:\/\/[^\s]+)/g);
        return parts.map(part => {
            if (part.match(/^https?:\/\//)) {
                return `<a href="${part}" target="_blank" class="notif-link">${part.includes('linkedin.com') ? 'View Post' : part}</a>`;
            }
            return part;
        }).join('');
    }).join('<br>');
}
