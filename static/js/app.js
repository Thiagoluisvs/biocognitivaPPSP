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
    // Bulk Actions & Row Selection
    const masterCheck = document.getElementById('selectAll');
    const rowChecks = document.querySelectorAll('.row-select');
    const bulkBar = document.getElementById('bulkActionsBar');
    const selectedCount = document.getElementById('selectedCount');

    function updateBulkBar() {
        const selected = Array.from(rowChecks).filter(c => c.checked);
        const count = selected.length;
        
        if (count > 0) {
            selectedCount.textContent = count;
            bulkBar.classList.add('active');
        } else {
            bulkBar.classList.remove('active');
        }
    }

    if (masterCheck) {
        masterCheck.addEventListener('change', () => {
            rowChecks.forEach(c => {
                c.checked = masterCheck.checked;
                c.closest('tr').classList.toggle('selected', c.checked);
            });
            updateBulkBar();
        });
    }

    rowChecks.forEach(c => {
        c.addEventListener('change', () => {
            c.closest('tr').classList.toggle('selected', c.checked);
            masterCheck.checked = Array.from(rowChecks).every(rc => rc.checked);
            updateBulkBar();
        });
    });

    // Individual action confirmations
    window.confirmAction = function(msg, url) {
        if (confirm(msg || 'Deseja realmente realizar esta ação?')) {
            window.location.href = url;
        }
    };

    // Bulk action submission
    window.submitBulkAction = function(action) {
        const ids = Array.from(rowChecks).filter(c => c.checked).map(c => c.value);
        if (ids.length === 0) return;
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/bulk-action/${action}`;
        
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'ids';
        input.value = JSON.stringify(ids);
        
        form.appendChild(input);
        document.body.appendChild(form);
        form.submit();
    };

    // Client-side filtering
    window.filterTable = function() {
        const input = document.getElementById('tableSearch');
        const filter = input.value.toLowerCase();
        const table = document.querySelector('.table');
        const rows = table.querySelectorAll('tbody tr');

        rows.forEach(row => {
            if (row.classList.contains('empty-state')) return;
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(filter) ? '' : 'none';
        });
    };
});
