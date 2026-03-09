class ToastManager {
    constructor() {
        this.container = document.createElement('div');
        this.container.id = 'toast-container';
        this.container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        `;
        document.body.appendChild(this.container);
    }

    show(message, type = 'success') {
        const toast = document.createElement('div');
        const colors = {
            success: '#10B981',
            error: '#EF4444',
            info: '#3B82F6'
        };
        toast.style.cssText = `
            background-color: #1F2937;
            color: #fff;
            padding: 12px 20px;
            border-radius: 8px;
            border-left: 4px solid ${colors[type] || colors.info};
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            transform: translateX(120%);
            transition: transform 0.3s ease-in-out;
            font-family: inherit;
            display: flex;
            align-items: center;
            gap: 10px;
        `;

        const icon = type === 'success' ? '✓' : type === 'error' ? '⚠' : 'ℹ';
        toast.innerHTML = `<span style="color: ${colors[type]}; font-weight: bold;">${icon}</span> <span>${message}</span>`;

        this.container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.style.transform = 'translateX(0)';
        });

        // Remove after 3 seconds
        setTimeout(() => {
            toast.style.transform = 'translateX(120%)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

const uxManager = {
    toast: new ToastManager(),

    getEmptyStateHTML(title, message, iconSVG = '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-gray-500 mb-4"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>') {
        return `
            <div class="empty-state" style="text-align: center; padding: 40px 20px; color: #9CA3AF;">
                <div style="display: flex; justify-content: center;">${iconSVG}</div>
                <h3 style="font-size: 1.125rem; font-weight: 500; color: #D1D5DB; margin-bottom: 8px;">${title}</h3>
                <p style="font-size: 0.875rem;">${message}</p>
            </div>
        `;
    },

    getSkeletonHTML() {
        return `
            <div style="padding: 20px; width: 100%;">
                <div class="skeleton skeleton-title"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
                <br>
                <div class="skeleton skeleton-box"></div>
            </div>
        `;
    }
};

// Expose globally for vanilla integrations
window.uxManager = uxManager;
window.ToastManager = ToastManager;
