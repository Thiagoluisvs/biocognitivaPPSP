// Portal Toxicologia ANAC - App JS
document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss flash messages
    document.querySelectorAll('.flash').forEach(el => {
        setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 5000);
    });
    // File drop zone
    const drop = document.getElementById('fileDrop');
    const input = document.getElementById('fileInput');
    if (drop && input) {
        drop.addEventListener('dragover', e => { e.preventDefault(); drop.style.borderColor = 'var(--accent)'; });
        drop.addEventListener('dragleave', () => { drop.style.borderColor = ''; });
        drop.addEventListener('drop', e => { e.preventDefault(); input.files = e.dataTransfer.files; drop.querySelector('p').textContent = e.dataTransfer.files[0].name; });
        input.addEventListener('change', () => { if (input.files[0]) drop.querySelector('p').textContent = input.files[0].name; });
    }
});
