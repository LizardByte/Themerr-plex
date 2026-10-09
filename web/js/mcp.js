import { api, toast } from './api.js';
import { _ } from './i18n.js';

export function initMcpTokens(signal) {
    const panel = document.getElementById('mcp');
    if (!panel) return;
    const form = document.getElementById('mcp-token-form');
    const list = document.getElementById('mcp-token-list');
    const reveal = document.getElementById('mcp-token-reveal');
    const credential = document.getElementById('mcp-new-token');
    const endpoint = document.getElementById('mcp-endpoint');
    const toggleToken = document.getElementById('mcp-toggle-token');
    const copyToken = document.getElementById('mcp-copy-token');
    const revokeAll = document.getElementById('mcp-revoke-all');
    let pending = false;
    let hasTokens = !revokeAll.disabled;
    let token = '';
    let tokenVisible = false;

    function setTokenVisible(visible) {
        tokenVisible = visible;
        credential.textContent = token ? (visible ? token : '•'.repeat(32)) : '';
        const label = visible ? _('Mask token') : _('Show token');
        toggleToken.setAttribute('aria-label', label);
        toggleToken.setAttribute('title', label);
        toggleToken.setAttribute('aria-pressed', String(visible));
        document.getElementById('mcp-show-token-icon').hidden = visible;
        document.getElementById('mcp-mask-token-icon').hidden = !visible;
    }

    function selectValue(element) {
        element.focus();
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(element);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function hideToken() {
        token = '';
        setTokenVisible(false);
        reveal.hidden = true;
    }

    function renderTokens(tokens) {
        const rows = tokens.map(token => {
            const row = document.createElement('div');
            row.className = 'mcp-token-row';
            const description = document.createElement('div');
            const name = document.createElement('strong');
            name.textContent = token.name;
            const details = document.createElement('p');
            const scope = token.scope === 'read' ? _('Read only') : _('Read and process');
            const invalidated = token.active ? '' : ` · ${_('Invalidated')}`;
            details.textContent = `${scope} · ${new Date(token.created).toLocaleString()}${invalidated}`;
            description.append(name, details);
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-outline-light';
            button.dataset.mcpRevoke = token.id;
            button.dataset.mcpMutation = '';
            button.textContent = _('Revoke');
            row.append(description, button);
            return row;
        });
        if (!rows.length) {
            const empty = document.createElement('p');
            empty.textContent = _('No MCP tokens created.');
            rows.push(empty);
        }
        list.replaceChildren(...rows);
        hasTokens = tokens.length > 0;
    }

    async function mutate(operation) {
        if (pending) return;
        pending = true;
        panel.querySelectorAll('[data-mcp-mutation]').forEach(button => { button.disabled = true; });
        form.setAttribute('aria-busy', 'true');
        try {
            await operation();
        } catch (error) {
            if (panel.isConnected && !signal?.aborted) toast(error.message, true);
        } finally {
            pending = false;
            panel.querySelectorAll('[data-mcp-mutation]').forEach(button => { button.disabled = false; });
            revokeAll.disabled = !hasTokens;
            form.removeAttribute('aria-busy');
        }
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        return mutate(async () => {
            hideToken();
            const result = await api('/api/mcp/tokens', { body: {
                name: document.getElementById('mcp-token-name').value,
                scope: document.getElementById('mcp-token-scope').value,
            } });
            if (!panel.isConnected || signal?.aborted) return;
            renderTokens(result.tokens);
            token = result.token;
            setTokenVisible(false);
            reveal.hidden = false;
            copyToken.focus();
            toast(_('MCP token created. Copy it into your client now.'));
        });
    });

    list.addEventListener('click', event => {
        const button = event.target.closest('[data-mcp-revoke]');
        if (!button || !list.contains(button)) return;
        return mutate(async () => {
            const result = await api(`/api/mcp/tokens/${encodeURIComponent(button.dataset.mcpRevoke)}`, { method: 'DELETE' });
            if (!panel.isConnected || signal?.aborted) return;
            hideToken();
            renderTokens(result.tokens);
            toast(result.message);
        });
    });

    revokeAll.addEventListener('click', () => {
        if (pending || !window.confirm(_('Revoke all MCP tokens and disconnect every client?'))) return;
        return mutate(async () => {
            const result = await api('/api/mcp/tokens', { method: 'DELETE' });
            if (!panel.isConnected || signal?.aborted) return;
            hideToken();
            renderTokens(result.tokens);
            toast(result.message);
        });
    });

    document.getElementById('mcp-copy-endpoint').addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(endpoint.textContent.trim());
            if (!panel.isConnected || signal?.aborted) return;
            toast(_('Endpoint URL copied.'));
        } catch {
            if (!panel.isConnected || signal?.aborted) return;
            selectValue(endpoint);
            toast(_('Copy the selected endpoint URL manually.'), true);
        }
    });
    toggleToken.addEventListener('click', () => {
        if (token) setTokenVisible(!tokenVisible);
    });
    copyToken.addEventListener('click', async () => {
        if (!token) return;
        const copiedToken = token;
        try {
            await navigator.clipboard.writeText(copiedToken);
            if (!panel.isConnected || signal?.aborted || token !== copiedToken) return;
            toast(_('MCP token copied.'));
        } catch {
            if (!panel.isConnected || signal?.aborted || token !== copiedToken) return;
            if (tokenVisible) {
                selectValue(credential);
                toast(_('Copy the selected token manually.'), true);
            } else {
                toggleToken.focus();
                toast(_('Unable to copy. Show the token to copy it manually.'), true);
            }
        }
    });
    document.getElementById('mcp-hide-token').addEventListener('click', hideToken);
    signal?.addEventListener('abort', hideToken, { once: true });
}
