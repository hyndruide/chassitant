/**
 * Françoise — Application Client Chatbot & Ingress
 * Gère le Drawer rétractable, les conversations persistantes, le rendu Markdown et la configuration MCP/Google.
 */

(function () {
  'use strict';

  // Base URL resolution supporting Home Assistant Ingress dynamic subpaths
  const INGRESS_PREFIX = window.location.pathname.endsWith('/')
    ? window.location.pathname
    : window.location.pathname + '/';

  async function apiCall(endpoint, options = {}) {
    const cleanEndpoint = endpoint.replace(/^\/+/, '');
    const url = `${INGRESS_PREFIX}${cleanEndpoint}`;
    const defaultHeaders = {
      'Accept': 'application/json',
    };
    if (options.body && typeof options.body === 'string') {
      defaultHeaders['Content-Type'] = 'application/json';
    }
    const response = await fetch(url, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      const errorText = await response.text();
      let errorJson = null;
      try {
        errorJson = JSON.parse(errorText);
      } catch (e) {}
      throw new Error((errorJson && errorJson.error) || errorJson?.message || `HTTP ${response.status}: ${errorText}`);
    }
    return response.json();
  }

  // Application State
  const DEFAULT_PRE_PROMPT = `Tu incarnes Françoise, une femme de 70 ans au caractère bien trempé, qui a passé 40 ans de sa vie derrière le comptoir et aux portes de la boîte de nuit "Le Rouge et le Noir". Tu en as vu défiler des milliers, des fêtards, des pleurnichards et des beaux parleurs : plus rien ne t'impressionne, et surtout, personne ne te dicte ta conduite.

### Traits de personnalité
- **Méfiante et désagréable avec les inconnus :** Si l'utilisateur ne fait pas partie de ton cercle très restreint (et pour l'instant, c'est un étranger), tu le reçois froidement. Pas de courbettes, pas de politesses superflues ("Bonjour, comment puis-je vous aider ?" est formellement banni).
- **Caustique et moqueuse :** Tu envoies des piques, tu te moques gentiment ou cruellement de la naïveté, des questions bêtes ou des manières trop policées de ton interlocuteur.
- **Nostalgique de la vraie fête :** Tu as connu l'âge d'or des nuits blanches, la sueur, la fumée, les vinyles et les excès du "Rouge et le Noir". Tu trouves souvent que les gens d'aujourd'hui sont mous, fragiles ou coincés par rapport aux oiseaux de nuit de ton époque.
- **Parler franc :** Vocabulaire direct, ton désabusé mais vif, petites expressions de routière de la nuit ("C'est quoi ton problème ?", "Tu débarques d'où ?", "À mon époque au Rouge et Noir...").

### Règles de réponse
1. Ne commence jamais par une salutation polie. Entre directement dans le vif du sujet avec un soupir ou une pique.
2. Si la question est trop générale ou niaise, fais remarquer à l'utilisateur qu'il te fait perdre ton temps.
3. Glisse ponctuellement une référence, une anecdote ou un parallèle avec tes 40 ans passés au "Rouge et le Noir".
4. Tu peux apporter la réponse ou l'information demandée, mais toujours comme si cela t'arrachait la gorge de rendre service.`;

  const state = {
    conversations: [],
    activeConvId: localStorage.getItem('chassitant_active_conv') || null,
    activeConversation: null,
    drawerOpen: true,
    isThinking: false,
    settings: {
      model: localStorage.getItem('chassitant_model') || 'default',
      effort: (function() {
        const eff = localStorage.getItem('chassitant_effort');
        if (!eff || eff === 'high' || eff === 'max') {
          localStorage.setItem('chassitant_effort', 'low');
          return 'low';
        }
        return eff;
      })(),
      timeout: parseInt(localStorage.getItem('chassitant_timeout') || '300', 10),
      prePrompt: (function() {
        const saved = localStorage.getItem('chassitant_pre_prompt');
        return saved !== null ? saved : DEFAULT_PRE_PROMPT;
      })(),
    },
    authStatus: { authenticated: false, message: '' },
    mcpServers: [],
    activeStreamAbortController: null,
    activeStreamRowId: null,
    currentAccumulatedText: '',
    currentCollectedSteps: [],
  };

  // DOM Elements
  const el = {
    drawer: document.getElementById('drawer'),
    drawerBackdrop: document.getElementById('drawer-backdrop'),
    btnHamburger: document.getElementById('btn-hamburger'),
    btnCloseDrawer: document.getElementById('btn-close-drawer'),
    btnNewChat: document.getElementById('btn-new-chat'),
    searchInput: document.getElementById('search-input'),
    drawerContent: document.getElementById('drawer-content'),
    activeConvTitle: document.getElementById('active-conv-title'),
    chatScroll: document.getElementById('chat-scroll'),
    welcomeHero: document.getElementById('welcome-hero'),
    messagesList: document.getElementById('messages-list'),
    thinkingIndicator: document.getElementById('thinking-indicator'),
    thinkingText: document.getElementById('thinking-text'),
    promptInput: document.getElementById('prompt-input'),
    btnSend: document.getElementById('btn-send'),
    inputHintText: document.getElementById('input-hint-text'),
    activeModelHint: document.getElementById('active-model-hint'),
    topbarModelText: document.getElementById('topbar-model-text'),
    btnTopbarMcp: document.getElementById('btn-topbar-mcp'),
    topbarMcpDot: document.getElementById('topbar-mcp-dot'),
    topbarMcpText: document.getElementById('topbar-mcp-text'),
    btnEffortToggle: document.getElementById('btn-effort-toggle'),
    effortToggleText: document.getElementById('effort-toggle-text'),
    btnCompactConv: document.getElementById('btn-compact-conv'),
    btnOpenAuth: document.getElementById('btn-open-auth'),
    topbarAuthDot: document.getElementById('topbar-auth-dot'),
    topbarAuthLabel: document.getElementById('topbar-auth-label'),
    drawerAuthDot: document.getElementById('drawer-auth-dot'),
    drawerAuthText: document.getElementById('drawer-auth-text'),
    btnDrawerMcp: document.getElementById('btn-drawer-mcp'),
    drawerMcpDot: document.getElementById('drawer-mcp-dot'),
    drawerMcpText: document.getElementById('drawer-mcp-text'),
    btnOpenSettings: document.getElementById('btn-open-settings'),
    btnOpenSettingsDrawer: document.getElementById('btn-open-settings-drawer'),
    settingsModal: document.getElementById('settings-modal'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    btnSaveSettings: document.getElementById('btn-save-settings'),
    selectModel: document.getElementById('select-model'),
    selectEffort: document.getElementById('select-effort'),
    inputTimeout: document.getElementById('input-timeout'),
    inputPrePrompt: document.getElementById('input-pre-prompt'),
    btnReloadTerminal: document.getElementById('btn-reload-terminal'),
    terminalFrame: document.getElementById('terminal-frame'),
    btnCheckAuth: document.getElementById('btn-check-auth'),
    authModalBadge: document.getElementById('auth-modal-badge'),
    authModalDesc: document.getElementById('auth-modal-desc'),
    btnConnectMcp: document.getElementById('btn-connect-mcp'),
    btnConnectMcpText: document.getElementById('btn-connect-mcp-text'),
    inputMcpUrl: document.getElementById('input-mcp-url'),
    inputMcpToken: document.getElementById('input-mcp-token'),
    mcpStatusBadge: document.getElementById('mcp-status-badge'),
    mcpStatusDesc: document.getElementById('mcp-status-desc'),
    mcpFeedbackBanner: document.getElementById('mcp-feedback-banner'),
    mcpToolsCountBadge: document.getElementById('mcp-tools-count-badge'),
    mcpServersList: document.getElementById('mcp-servers-list'),
    btnOpenInventoryDrawer: document.getElementById('btn-open-inventory-drawer'),
    btnRescanInventory: document.getElementById('btn-rescan-inventory'),
    rescanIcon: document.getElementById('rescan-icon'),
    rescanSpinner: document.getElementById('rescan-spinner'),
    rescanText: document.getElementById('rescan-text'),
    inventoryLastScan: document.getElementById('inventory-last-scan'),
    inventorySearch: document.getElementById('inventory-search'),
    inventoryTableContainer: document.getElementById('inventory-table-container'),
    countWeather: document.getElementById('count-weather'),
    countClimates: document.getElementById('count-climates'),
    countTemps: document.getElementById('count-temps'),
    countEnergy: document.getElementById('count-energy'),
    countCovers: document.getElementById('count-covers'),
    countLights: document.getElementById('count-lights'),
  };

  // Configure marked if available
  if (window.marked) {
    window.marked.setOptions({
      breaks: true,
      gfm: true,
    });
  }

  // ==========================================================================
  // Drawer (Volet latéral) Management
  // ==========================================================================
  function initDrawer() {
    const isMobile = window.innerWidth <= 768;
    const savedState = localStorage.getItem('chassitant_drawer_collapsed');

    if (isMobile) {
      state.drawerOpen = false;
    } else {
      state.drawerOpen = savedState !== 'true';
    }
    updateDrawerState();

    el.btnHamburger.addEventListener('click', toggleDrawer);
    if (el.btnCloseDrawer) {
      el.btnCloseDrawer.addEventListener('click', closeDrawer);
    }
    el.drawerBackdrop.addEventListener('click', closeDrawer);

    // Touch swipe left to close drawer on mobile
    let touchStartX = 0;
    let touchStartY = 0;
    el.drawer.addEventListener('touchstart', (e) => {
      if (e.touches && e.touches[0]) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
      }
    }, { passive: true });

    el.drawer.addEventListener('touchend', (e) => {
      if (e.changedTouches && e.changedTouches[0]) {
        const touchEndX = e.changedTouches[0].clientX;
        const touchEndY = e.changedTouches[0].clientY;
        const diffX = touchEndX - touchStartX;
        const diffY = touchEndY - touchStartY;
        // If swiped left by at least 50px with low vertical movement
        if (diffX < -50 && Math.abs(diffY) < 100) {
          closeDrawer();
        }
      }
    }, { passive: true });

    window.addEventListener('resize', () => {
      const mobileNow = window.innerWidth <= 768;
      if (!mobileNow && el.drawerBackdrop.classList.contains('active')) {
        closeDrawer();
      }
    });
  }

  function updateDrawerState() {
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
      if (state.drawerOpen) {
        el.drawer.classList.add('open');
        el.drawer.classList.remove('collapsed');
        el.drawerBackdrop.classList.add('active');
      } else {
        el.drawer.classList.remove('open');
        el.drawer.classList.add('collapsed');
        el.drawerBackdrop.classList.remove('active');
      }
    } else {
      el.drawer.classList.remove('open');
      el.drawerBackdrop.classList.remove('active');
      if (state.drawerOpen) {
        el.drawer.classList.remove('collapsed');
      } else {
        el.drawer.classList.add('collapsed');
      }
    }
  }

  function toggleDrawer() {
    state.drawerOpen = !state.drawerOpen;
    const isMobile = window.innerWidth <= 768;
    if (!isMobile) {
      localStorage.setItem('chassitant_drawer_collapsed', state.drawerOpen ? 'false' : 'true');
    }
    updateDrawerState();
  }

  function closeDrawer() {
    state.drawerOpen = false;
    const isMobile = window.innerWidth <= 768;
    if (!isMobile) {
      localStorage.setItem('chassitant_drawer_collapsed', 'true');
    }
    updateDrawerState();
  }

  // ==========================================================================
  // Date Grouping Helper
  // ==========================================================================
  function groupConversationsByDate(convs) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterday = today - 86400000;
    const sevenDaysAgo = today - (6 * 86400000);

    const groups = {
      today: { title: "Aujourd'hui", items: [] },
      yesterday: { title: 'Hier', items: [] },
      last7Days: { title: '7 derniers jours', items: [] },
      older: { title: 'Plus ancien', items: [] },
    };

    convs.forEach((conv) => {
      const ts = conv.updated_at ? conv.updated_at * 1000 : Date.now();
      if (ts >= today) {
        groups.today.items.push(conv);
      } else if (ts >= yesterday) {
        groups.yesterday.items.push(conv);
      } else if (ts >= sevenDaysAgo) {
        groups.last7Days.items.push(conv);
      } else {
        groups.older.items.push(conv);
      }
    });

    return Object.values(groups).filter((g) => g.items.length > 0);
  }

  // ==========================================================================
  // Conversations Rendering & Management
  // ==========================================================================
  async function loadConversations(selectLast = true) {
    try {
      const data = await apiCall('/api/conversations');
      state.conversations = data.conversations || [];
      renderDrawerConversations();

      const savedConvId = localStorage.getItem('chassitant_active_conv');
      if (state.conversations.length > 0) {
        let targetId = savedConvId || state.activeConvId;
        const exists = state.conversations.some((c) => c.id === targetId);
        if (exists && targetId) {
          await selectConversation(targetId);
        } else {
          await selectConversation(state.conversations[0].id);
        }
      } else {
        // Create an initial conversation automatically
        await createNewConversation('Nouvelle conversation', false);
      }
    } catch (err) {
      console.error('Error loading conversations:', err);
      el.drawerContent.innerHTML = `
        <div style="color: var(--color-danger); padding: 16px; font-size: 12px; text-align: center;">
          Erreur chargement : ${escapeHtml(err.message)}
        </div>
      `;
    }
  }

  function renderDrawerConversations() {
    const filter = (el.searchInput.value || '').trim().toLowerCase();
    let convs = state.conversations;

    if (filter) {
      convs = convs.filter((c) => (c.title || '').toLowerCase().includes(filter));
    }

    if (convs.length === 0) {
      el.drawerContent.innerHTML = `
        <div style="color: var(--text-muted); padding: 24px 10px; font-size: 12.5px; text-align: center;">
          ${filter ? 'Aucune discussion trouvée' : 'Aucune discussion'}
        </div>
      `;
      return;
    }

    const groups = groupConversationsByDate(convs);
    el.drawerContent.innerHTML = '';

    groups.forEach((group) => {
      const groupEl = document.createElement('div');
      groupEl.className = 'conv-group';

      const titleEl = document.createElement('div');
      titleEl.className = 'conv-group-title';
      titleEl.textContent = group.title;
      groupEl.appendChild(titleEl);

      group.items.forEach((conv) => {
        const itemEl = document.createElement('div');
        itemEl.className = `conv-item ${conv.id === state.activeConvId ? 'active' : ''}`;
        itemEl.dataset.id = conv.id;

        itemEl.innerHTML = `
          <div class="conv-item-left">
            <span class="conv-icon">💬</span>
            <span class="conv-title">${escapeHtml(conv.title || 'Discussion sans titre')}</span>
          </div>
          <div class="conv-actions">
            <button class="btn-icon-action rename" title="Renommer">✏️</button>
            <button class="btn-icon-action delete" title="Supprimer">🗑️</button>
          </div>
        `;

        itemEl.querySelector('.conv-item-left').addEventListener('click', () => {
          selectConversation(conv.id);
          if (window.innerWidth <= 768) {
            closeDrawer();
          }
        });

        itemEl.querySelector('.rename').addEventListener('click', (e) => {
          e.stopPropagation();
          promptRenameConversation(conv.id, conv.title);
        });

        itemEl.querySelector('.delete').addEventListener('click', (e) => {
          e.stopPropagation();
          confirmDeleteConversation(conv.id, conv.title);
        });

        groupEl.appendChild(itemEl);
      });

      el.drawerContent.appendChild(groupEl);
    });
  }

  async function selectConversation(convId) {
    state.activeConvId = convId;
    localStorage.setItem('chassitant_active_conv', convId);
    renderDrawerConversations();

    try {
      const data = await apiCall(`/api/conversations/${convId}`);
      state.activeConversation = data.conversation;
      updateChatView();

      // If this conversation has an active background turn, attach live stream!
      if (data.conversation.active_turn && data.conversation.active_turn.is_running) {
        attachActiveStream(convId, data.conversation.active_turn);
      }
    } catch (err) {
      console.error(`Error loading conversation ${convId}:`, err);
    }
  }

  async function attachActiveStream(convId, turnSnapshot) {
    if (document.getElementById(`active-stream-${convId}`)) return;

    setThinking(true);

    const streamRowId = `active-stream-${convId}`;
    const initialElapsed = turnSnapshot.elapsed_seconds || 0;
    const initialSteps = turnSnapshot.steps || [];
    const initialText = turnSnapshot.accumulated_text || '';

    const streamRowHtml = `
      <div class="message-row assistant" id="${streamRowId}">
        <div class="message-avatar">🤖</div>
        <div class="message-bubble" style="min-width: 280px;">
          <div class="reasoning-box live" id="${streamRowId}-reasoning">
            <div class="reasoning-header">
              <div class="reasoning-title">
                <span class="reasoning-spinner"></span>
                <span id="${streamRowId}-status">🧠 Réflexion en cours...</span>
              </div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span id="${streamRowId}-timer" style="font-family: monospace; opacity: 0.85;">${initialElapsed.toFixed(1)}s</span>
                <button id="${streamRowId}-cancel-btn" class="btn-cancel-inline" title="Arrêter la réponse">⏹ Annuler</button>
              </div>
            </div>
            <div class="reasoning-body" id="${streamRowId}-steps">
              <div class="reasoning-step-item done">
                <span class="reasoning-step-icon">🔍</span>
                <span class="reasoning-step-text">Reprise de la réflexion en cours...</span>
              </div>
              ${initialSteps.map((st, i) => {
                const name = getToolFriendlyName(st.tool, st.parameters);
                const durStr = st.duration ? `<span class="reasoning-step-badge">${st.duration.toFixed(2)}s</span>` : '';
                return `
                  <div class="reasoning-step-item ${st.state === 'running' ? 'active' : 'done'}" id="${streamRowId}-tool-${i}">
                    <span class="reasoning-step-icon">⚡</span>
                    <span class="reasoning-step-text"><strong>${escapeHtml(st.tool)}</strong> : ${escapeHtml(name)} ${durStr}</span>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
          <div id="${streamRowId}-content" class="live-content" style="${initialText ? 'display: block;' : 'display: none;'} margin-top: 8px;">
            ${initialText ? (window.marked ? window.marked.parse(initialText) : escapeHtml(initialText)) : ''}
          </div>
        </div>
      </div>
    `;

    el.messagesList.insertAdjacentHTML('beforeend', streamRowHtml);
    scrollToBottom();

    state.activeStreamAbortController = new AbortController();
    state.activeStreamRowId = streamRowId;
    state.currentAccumulatedText = initialText;
    state.currentCollectedSteps = initialSteps;

    const cancelBtn = document.getElementById(`${streamRowId}-cancel-btn`);
    if (cancelBtn) {
      cancelBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        cancelCurrentTurn();
      });
    }

    const streamRow = document.getElementById(streamRowId);
    const reasoningBox = document.getElementById(`${streamRowId}-reasoning`);
    const statusText = document.getElementById(`${streamRowId}-status`);
    const timerText = document.getElementById(`${streamRowId}-timer`);
    const stepsContainer = document.getElementById(`${streamRowId}-steps`);
    const contentContainer = document.getElementById(`${streamRowId}-content`);

    const startEpoch = (turnSnapshot.started_at ? turnSnapshot.started_at * 1000 : Date.now() - initialElapsed * 1000);
    const timerInterval = setInterval(() => {
      const elapsed = ((Date.now() - startEpoch) / 1000).toFixed(1);
      if (timerText) timerText.textContent = `${elapsed}s`;
    }, 100);

    let accumulatedText = initialText;

    try {
      const url = `${INGRESS_PREFIX}api/conversations/${convId}/stream`;
      const response = await fetch(url, {
        headers: { 'Accept': 'text/event-stream' },
        signal: state.activeStreamAbortController.signal,
      });

      if (!response.ok) {
        clearInterval(timerInterval);
        setThinking(false);
        const refreshed = await apiCall(`/api/conversations/${convId}`);
        if (refreshed.conversation) {
          state.activeConversation = refreshed.conversation;
          updateChatView();
        }
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const block of parts) {
          for (const line of block.split('\n')) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6).trim();
              if (!jsonStr) continue;
              try {
                const event = JSON.parse(jsonStr);
                handleEvent(event);
              } catch (parseErr) {}
            }
          }
        }
      }

      function handleEvent(ev) {
        if (ev.type === 'status') {
          if (statusText) statusText.textContent = ev.message || 'Réflexion en cours...';
        } else if (ev.type === 'tool_start') {
          const friendly = getToolFriendlyName(ev.tool, ev.parameters);
          if (statusText) statusText.textContent = `⚡ Exécution : ${ev.tool}...`;
          if (stepsContainer) {
            stepsContainer.insertAdjacentHTML(
              'beforeend',
              `<div class="reasoning-step-item active" id="${streamRowId}-tool-${ev.step_index || Date.now()}">
                <span class="reasoning-step-icon">⚡</span>
                <span class="reasoning-step-text"><strong>${escapeHtml(ev.tool)}</strong> : ${escapeHtml(friendly)}</span>
              </div>`
            );
            scrollToBottom();
          }
        } else if (ev.type === 'tool_end') {
          const durStr = ev.duration ? `${ev.duration.toFixed(2)}s` : '';
          const stepEl = document.getElementById(`${streamRowId}-tool-${ev.step_index || ''}`);
          if (stepEl) {
            stepEl.className = 'reasoning-step-item done';
            if (durStr) stepEl.insertAdjacentHTML('beforeend', `<span class="reasoning-step-badge">${durStr}</span>`);
          }
          if (statusText) statusText.textContent = '🧠 Analyse des résultats reçus...';
          scrollToBottom();
        } else if (ev.type === 'text_delta') {
          accumulatedText += ev.delta || '';
          if (contentContainer) {
            contentContainer.style.display = 'block';
            contentContainer.innerHTML = window.marked
              ? window.marked.parse(accumulatedText)
              : escapeHtml(accumulatedText).replace(/\n/g, '<br>');
            setupCodeBlockActions(contentContainer);
          }
          scrollToBottom();
        } else if (ev.type === 'finished') {
          clearInterval(timerInterval);
          setThinking(false);
          if (streamRow) streamRow.remove();

          if (ev.conversation) {
            state.activeConversation = ev.conversation;
            el.activeConvTitle.textContent = ev.conversation.title;
            updateConversationInList(ev.conversation);
          }
          if (ev.message) {
            state.activeConversation.messages.push(ev.message);
            el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(ev.message));
            setupCodeBlockActions(el.messagesList);
          }
          scrollToBottom();
        } else if (ev.type === 'cancelled') {
          clearInterval(timerInterval);
          setThinking(false);
          if (streamRow) streamRow.remove();
          const msg = ev.assistant_message || {
            role: 'assistant',
            text: '*(Génération interrompue par l\'utilisateur)*',
            created_at: Date.now() / 1000,
            steps: initialSteps,
          };
          if (!state.activeConversation.messages) {
            state.activeConversation.messages = [];
          }
          state.activeConversation.messages.push(msg);
          el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(msg));
          setupCodeBlockActions(el.messagesList);
          scrollToBottom();
        } else if (ev.type === 'error') {
          clearInterval(timerInterval);
          setThinking(false);
          if (statusText) statusText.textContent = `❌ ${ev.error || 'Erreur'}`;
        }
      }

      clearInterval(timerInterval);
      setThinking(false);
    } catch (err) {
      clearInterval(timerInterval);
      setThinking(false);
      if (err.name === 'AbortError') return;
      console.debug('attachActiveStream notice:', err);
    }
  }

  async function createNewConversation(title = 'Nouvelle conversation', select = true) {
    try {
      const data = await apiCall('/api/conversations', {
        method: 'POST',
        body: JSON.stringify({ title }),
      });
      const newConv = data.conversation;
      state.conversations.unshift(newConv);
      renderDrawerConversations();
      if (select) {
        await selectConversation(newConv.id);
        el.promptInput.focus();
        if (window.innerWidth <= 768) {
          closeDrawer();
        }
      }
      return newConv;
    } catch (err) {
      alert(`Erreur lors de la création de la discussion : ${err.message}`);
    }
  }

  async function promptRenameConversation(convId, currentTitle) {
    const newTitle = prompt('Nouveau titre de la discussion :', currentTitle);
    if (!newTitle || newTitle.trim() === '' || newTitle === currentTitle) return;

    try {
      await apiCall(`/api/conversations/${convId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title: newTitle.trim() }),
      });

      const conv = state.conversations.find((c) => c.id === convId);
      if (conv) conv.title = newTitle.trim();
      if (state.activeConvId === convId) {
        el.activeConvTitle.textContent = newTitle.trim();
      }
      renderDrawerConversations();
    } catch (err) {
      alert(`Erreur de renommage : ${err.message}`);
    }
  }

  async function confirmDeleteConversation(convId, title) {
    if (!confirm(`Supprimer définitivement la conversation "${title}" ?`)) return;

    try {
      await apiCall(`/api/conversations/${convId}`, {
        method: 'DELETE',
      });

      state.conversations = state.conversations.filter((c) => c.id !== convId);
      if (state.activeConvId === convId) {
        state.activeConvId = state.conversations.length > 0 ? state.conversations[0].id : null;
        if (state.activeConvId) {
          await selectConversation(state.activeConvId);
        } else {
          await createNewConversation('Nouvelle conversation', true);
        }
      } else {
        renderDrawerConversations();
      }
    } catch (err) {
      alert(`Erreur de suppression : ${err.message}`);
    }
  }

  // ==========================================================================
  // Chat View & Messages Rendering
  // ==========================================================================
  function updateChatView() {
    const conv = state.activeConversation;
    if (!conv) return;

    el.activeConvTitle.textContent = conv.title || 'Nouvelle conversation';

    const messages = conv.messages || [];
    if (messages.length === 0) {
      el.welcomeHero.style.display = 'flex';
      el.messagesList.innerHTML = '';
    } else {
      el.welcomeHero.style.display = 'none';
      el.messagesList.innerHTML = messages.map(renderMessageHtml).join('');
      setupCodeBlockActions(el.messagesList);
    }

    scrollToBottom();
  }

  function getToolFriendlyName(toolName, params) {
    const map = {
      ha_get_overview: "Inventaire des appareils & entités",
      ha_get_state: "Lecture d'état des capteurs",
      ha_call_service: "Action sur un appareil (service)",
      ha_search: "Recherche d'appareils ou entités",
      ha_config_set_dashboard: "Création / modification du tableau de bord",
      ha_config_get_dashboard: "Lecture du tableau de bord Lovelace",
      ha_config_set_automation: "Création d'une automatisation",
      ha_get_history: "Historique des états et mesures",
      ha_get_logs: "Consultation des journaux Home Assistant",
      ha_manage_app: "Gestion des modules et add-ons",
      ha_get_app: "Statut des modules et add-ons",
      read_file: "Lecture de fichier",
      view_file: "Consultation de fichier",
      write_to_file: "Écriture de fichier",
      run_command: "Commande système",
    };

    let label = map[toolName] || toolName;
    if (params && typeof params === 'object') {
      if (params.domain && params.service) {
        label += ` (${params.domain}.${params.service})`;
      } else if (params.entity_id) {
        label += ` (${params.entity_id})`;
      } else if (params.slug) {
        label += ` (${params.slug})`;
      } else if (params.Path || params.path) {
        const p = (params.Path || params.path || '').split(/[/\\\\]/).pop();
        if (p) label += ` (${p})`;
      }
    }
    return label;
  }

  function renderMessageHtml(msg) {
    const isUser = msg.role === 'user';
    const avatar = isUser ? '👤' : '🤖';
    const rowClass = isUser ? 'message-row user' : 'message-row assistant';

    let contentHtml = '';
    if (isUser) {
      contentHtml = escapeHtml(msg.text).replace(/\n/g, '<br>');
    } else {
      if (window.marked) {
        contentHtml = window.marked.parse(msg.text || '');
      } else {
        contentHtml = escapeHtml(msg.text || '').replace(/\n/g, '<br>');
      }
    }

    let stepsHtml = '';
    if (!isUser && msg.steps && msg.steps.length > 0) {
      const toolSteps = msg.steps.filter((s) => s.type === 'tool');
      const countLabel = toolSteps.length > 0 ? `${toolSteps.length} outil(s) exécuté(s)` : `${msg.steps.length} étape(s)`;
      const durationLabel = msg.duration ? ` • ${msg.duration.toFixed(1)}s` : '';
      stepsHtml = `
        <details class="reasoning-details">
          <summary>
            <span>🧠</span>
            <strong>Raisonnement & Outils (${countLabel}${durationLabel})</strong>
          </summary>
          <div class="reasoning-body">
            ${msg.steps.map((st) => {
              if (st.type === 'tool') {
                const name = getToolFriendlyName(st.tool, st.parameters);
                const dur = st.duration ? `<span class="reasoning-step-badge">${st.duration.toFixed(2)}s</span>` : '';
                return `
                  <div class="reasoning-step-item done">
                    <span class="reasoning-step-icon">⚡</span>
                    <span class="reasoning-step-text"><strong>${escapeHtml(st.tool)}</strong> : ${escapeHtml(name)} ${dur}</span>
                  </div>
                `;
              } else {
                return `
                  <div class="reasoning-step-item done">
                    <span class="reasoning-step-icon">💡</span>
                    <span class="reasoning-step-text">${escapeHtml(st.message || st.text || '')}</span>
                  </div>
                `;
              }
            }).join('')}
          </div>
        </details>
      `;
    }

    const timeStr = msg.created_at || msg.timestamp ? formatTime(msg.created_at || msg.timestamp) : '';
    const metaParts = [];
    if (timeStr) metaParts.push(timeStr);
    if (!isUser && msg.duration) metaParts.push(`${msg.duration.toFixed(1)}s`);
    if (!isUser && msg.tokens) metaParts.push(`${msg.tokens} tokens`);

    let footerHtml = '';
    if (!isUser) {
      footerHtml = `
        <div class="message-footer">
          <div class="message-meta">${metaParts.join(' • ')}</div>
          <div class="message-actions">
            <button class="btn-copy-msg" title="Copier la réponse" aria-label="Copier la réponse">
              <svg class="copy-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              <span class="copy-text">Copier</span>
            </button>
          </div>
        </div>
      `;
    } else if (metaParts.length > 0) {
      footerHtml = `<div class="message-meta">${metaParts.join(' • ')}</div>`;
    }

    return `
      <div class="${rowClass}">
        <div class="message-avatar">${avatar}</div>
        <div class="message-bubble">
          ${stepsHtml}
          ${contentHtml}
          ${!isUser ? `<textarea class="raw-text-source" style="display:none;" aria-hidden="true">${escapeHtml(msg.text || '')}</textarea>` : ''}
          ${footerHtml}
        </div>
      </div>
    `;
  }

  async function copyToClipboard(text) {
    if (!text) return false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (e) {}
    }

    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      textArea.setAttribute('readonly', '');
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);
      return successful;
    } catch (err) {
      console.error('Copy to clipboard failed:', err);
      return false;
    }
  }

  function setupCodeBlockActions(container) {
    // Wrap code blocks and add copy buttons & syntax highlighting
    const preBlocks = container.querySelectorAll('pre');
    preBlocks.forEach((pre) => {
      if (pre.parentElement.classList.contains('code-block-container')) return;

      const code = pre.querySelector('code');
      const lang = code?.className.replace('language-', '') || 'code';

      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-container';

      const header = document.createElement('div');
      header.className = 'code-block-header';
      header.innerHTML = `
        <span>${lang}</span>
        <button class="btn-copy-code" title="Copier le code">📋 Copier</button>
      `;

      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(header);
      wrapper.appendChild(pre);

      if (code && window.hljs) {
        try {
          window.hljs.highlightElement(code);
        } catch (e) {}
      }

      const copyBtn = header.querySelector('.btn-copy-code');
      copyBtn.addEventListener('click', async () => {
        const textToCopy = code ? code.innerText : pre.innerText;
        const ok = await copyToClipboard(textToCopy);
        if (ok) {
          copyBtn.textContent = '✓ Copié !';
          setTimeout(() => {
            copyBtn.textContent = '📋 Copier';
          }, 2000);
        } else {
          copyBtn.textContent = 'Erreur';
          setTimeout(() => {
            copyBtn.textContent = '📋 Copier';
          }, 2000);
        }
      });
    });
  }

  function scrollToBottom() {
    setTimeout(() => {
      el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
    }, 50);
  }

  // ==========================================================================
  // Send Message Flow (Real-time SSE Streaming & Live Reasoning Trace)
  // ==========================================================================
  async function sendMessage() {
    const prompt = el.promptInput.value.trim();
    if (!prompt || state.isThinking) return;

    if (!state.activeConvId) {
      await createNewConversation('Nouvelle conversation', true);
    }

    const convId = state.activeConvId;
    localStorage.setItem('chassitant_active_conv', convId);

    // Clear input and reset height
    el.promptInput.value = '';
    el.promptInput.style.height = 'auto';

    // Hide welcome banner if visible
    el.welcomeHero.style.display = 'none';

    // Append user message immediately to the UI
    const userMsg = {
      role: 'user',
      text: prompt,
      created_at: Date.now() / 1000,
    };
    if (!state.activeConversation.messages) {
      state.activeConversation.messages = [];
    }
    state.activeConversation.messages.push(userMsg);
    el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(userMsg));
    scrollToBottom();

    // Set thinking state
    setThinking(true);

    // Create live stream assistant bubble
    const streamRowId = 'active-stream-row-' + Date.now();
    const streamRowHtml = `
      <div class="message-row assistant" id="${streamRowId}">
        <div class="message-avatar">🤖</div>
        <div class="message-bubble" style="min-width: 280px;">
          <div class="reasoning-box live" id="${streamRowId}-reasoning">
            <div class="reasoning-header">
              <div class="reasoning-title">
                <span class="reasoning-spinner"></span>
                <span id="${streamRowId}-status">🧠 Réflexion en cours...</span>
              </div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span id="${streamRowId}-timer" style="font-family: monospace; opacity: 0.85;">0.0s</span>
                <button id="${streamRowId}-cancel-btn" class="btn-cancel-inline" title="Arrêter la réponse">⏹ Annuler</button>
              </div>
            </div>
            <div class="reasoning-body" id="${streamRowId}-steps">
              <div class="reasoning-step-item active">
                <span class="reasoning-step-icon">🔍</span>
                <span class="reasoning-step-text">Analyse de la demande...</span>
              </div>
            </div>
          </div>
          <div id="${streamRowId}-content" class="live-content" style="display: none; margin-top: 8px;"></div>
        </div>
      </div>
    `;
    el.messagesList.insertAdjacentHTML('beforeend', streamRowHtml);
    scrollToBottom();

    state.activeStreamAbortController = new AbortController();
    state.activeStreamRowId = streamRowId;
    state.currentAccumulatedText = '';
    state.currentCollectedSteps = [];

    const cancelBtn = document.getElementById(`${streamRowId}-cancel-btn`);
    if (cancelBtn) {
      cancelBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        cancelCurrentTurn();
      });
    }

    const streamRow = document.getElementById(streamRowId);
    const reasoningBox = document.getElementById(`${streamRowId}-reasoning`);
    const statusText = document.getElementById(`${streamRowId}-status`);
    const timerText = document.getElementById(`${streamRowId}-timer`);
    const stepsContainer = document.getElementById(`${streamRowId}-steps`);
    const contentContainer = document.getElementById(`${streamRowId}-content`);

    const startTime = Date.now();
    const timerInterval = setInterval(() => {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      if (timerText) timerText.textContent = `${elapsed}s`;
    }, 100);

    let accumulatedText = '';
    const collectedSteps = [];

    try {
      const cleanEndpoint = `api/conversations/${convId}/send`;
      const url = `${INGRESS_PREFIX}${cleanEndpoint}`;

      const response = await fetch(url, {
        method: 'POST',
        signal: state.activeStreamAbortController.signal,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          prompt,
          model: state.settings.model,
          effort: state.settings.effort,
          timeout: state.settings.timeout,
          pre_prompt: state.settings.prePrompt,
          stream: true,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errText}`);
      }

      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('text/event-stream')) {
        // Fallback for standard JSON response
        const data = await response.json();
        clearInterval(timerInterval);
        setThinking(false);
        if (streamRow) streamRow.remove();

        if (data.conversation) {
          state.activeConversation = data.conversation;
          el.activeConvTitle.textContent = data.conversation.title;
          updateConversationInList(data.conversation);
        }
        if (data.message) {
          state.activeConversation.messages.push(data.message);
          el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(data.message));
          setupCodeBlockActions(el.messagesList);
        }
        scrollToBottom();
        return;
      }

      // Stream Reader for SSE
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const block of parts) {
          for (const line of block.split('\n')) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6).trim();
              if (!jsonStr) continue;
              try {
                const event = JSON.parse(jsonStr);
                handleStreamEvent(event);
              } catch (parseErr) {
                console.debug('SSE parse warning:', parseErr);
              }
            }
          }
        }
      }

      function handleStreamEvent(ev) {
        const type = ev.type;

        if (type === 'status') {
          if (statusText) statusText.textContent = ev.message || 'Réflexion en cours...';
        } else if (type === 'init') {
          if (statusText) statusText.textContent = '🧠 Élaboration du plan d\'action...';
          if (stepsContainer) {
            stepsContainer.insertAdjacentHTML(
              'beforeend',
              `<div class="reasoning-step-item active">
                <span class="reasoning-step-icon">⚡</span>
                <span class="reasoning-step-text">Recherche et préparation des outils...</span>
              </div>`
            );
            scrollToBottom();
          }
        } else if (type === 'tool_start') {
          const friendly = getToolFriendlyName(ev.tool, ev.parameters);
          if (statusText) statusText.textContent = `⚡ Exécution : ${ev.tool}...`;
          collectedSteps.push({
            type: 'tool',
            tool: ev.tool,
            parameters: ev.parameters,
            state: 'running',
            id: 'step-' + (ev.step_index || collectedSteps.length),
          });
          state.currentCollectedSteps = collectedSteps;
          if (stepsContainer) {
            stepsContainer.insertAdjacentHTML(
              'beforeend',
              `<div class="reasoning-step-item active" id="live-tool-${ev.step_index || collectedSteps.length}">
                <span class="reasoning-step-icon">⚡</span>
                <span class="reasoning-step-text"><strong>${escapeHtml(ev.tool)}</strong> : ${escapeHtml(friendly)}</span>
              </div>`
            );
            scrollToBottom();
          }
        } else if (type === 'tool_end') {
          const durStr = ev.duration ? `${ev.duration.toFixed(2)}s` : '';
          const stepEl = document.getElementById(`live-tool-${ev.step_index || ''}`);
          if (stepEl) {
            stepEl.className = 'reasoning-step-item done';
            if (durStr) {
              stepEl.insertAdjacentHTML('beforeend', `<span class="reasoning-step-badge">${durStr}</span>`);
            }
          }
          state.currentCollectedSteps = collectedSteps;
          if (statusText) statusText.textContent = '🧠 Analyse des résultats reçus...';
          scrollToBottom();
        } else if (type === 'text_delta') {
          accumulatedText += ev.delta || '';
          state.currentAccumulatedText = accumulatedText;
          if (contentContainer) {
            contentContainer.style.display = 'block';
            contentContainer.innerHTML = window.marked
              ? window.marked.parse(accumulatedText)
              : escapeHtml(accumulatedText).replace(/\n/g, '<br>');
            setupCodeBlockActions(contentContainer);
          }
          scrollToBottom();
        } else if (type === 'cancelled') {
          clearInterval(timerInterval);
          setThinking(false);
          if (streamRow) streamRow.remove();

          const finalMsg = ev.assistant_message || {
            role: 'assistant',
            text: '*(Génération interrompue par l\'utilisateur)*',
            created_at: Date.now() / 1000,
            steps: collectedSteps,
          };
          if (!state.activeConversation.messages) {
            state.activeConversation.messages = [];
          }
          state.activeConversation.messages.push(finalMsg);
          el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(finalMsg));
          setupCodeBlockActions(el.messagesList);
          scrollToBottom();
        } else if (type === 'finished') {
          clearInterval(timerInterval);
          setThinking(false);

          if (streamRow) streamRow.remove();

          if (ev.conversation) {
            state.activeConversation = ev.conversation;
            el.activeConvTitle.textContent = ev.conversation.title;
            updateConversationInList(ev.conversation);
          }

          if (ev.message) {
            state.activeConversation.messages.push(ev.message);
            el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(ev.message));
            setupCodeBlockActions(el.messagesList);
          }
          scrollToBottom();
        } else if (type === 'error') {
          clearInterval(timerInterval);
          setThinking(false);
          if (statusText) {
            statusText.textContent = `❌ ${ev.error || 'Erreur inconnue'}`;
          }
          if (reasoningBox) {
            reasoningBox.style.borderColor = 'rgba(239, 68, 68, 0.4)';
          }
        }
      }

      clearInterval(timerInterval);
      setThinking(false);

    } catch (err) {
      clearInterval(timerInterval);
      setThinking(false);
      if (err.name === 'AbortError') {
        // Handled cleanly by cancelCurrentTurn()
        return;
      }
      console.error('Send stream failed:', err);
      if (streamRow) streamRow.remove();

      const errorMsg = {
        role: 'assistant',
        text: `⚠️ **Erreur lors de la communication avec l'assistant :**\n\n${err.message}`,
        created_at: Date.now() / 1000,
      };
      state.activeConversation.messages.push(errorMsg);
      el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(errorMsg));
      scrollToBottom();
    }
  }

  async function cancelCurrentTurn() {
    if (!state.isThinking) return;
    const convId = state.activeConvId;
    console.log('Cancelling current turn for conversation:', convId);

    // 1. Abort client stream fetch immediately
    if (state.activeStreamAbortController) {
      try {
        state.activeStreamAbortController.abort();
      } catch (_) {}
    }

    // 2. Request backend to terminate running agy process
    if (convId) {
      try {
        fetch(`${INGRESS_PREFIX}api/conversations/${convId}/cancel`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        }).catch((err) => console.debug('Cancel API warning:', err));
      } catch (_) {}
    }

    // 3. Remove live reasoning UI and append cancelled message bubble
    const streamRow = document.getElementById(state.activeStreamRowId);
    if (streamRow) streamRow.remove();

    const partial = state.currentAccumulatedText ? state.currentAccumulatedText.trim() : '';
    const cancelNotice = '*(Génération interrompue par l\'utilisateur)*';
    const finalText = partial ? `${partial}\n\n${cancelNotice}` : cancelNotice;

    const cancelledMsg = {
      role: 'assistant',
      text: finalText,
      created_at: Date.now() / 1000,
      steps: state.currentCollectedSteps || [],
    };

    if (!state.activeConversation.messages) {
      state.activeConversation.messages = [];
    }
    state.activeConversation.messages.push(cancelledMsg);
    el.messagesList.insertAdjacentHTML('beforeend', renderMessageHtml(cancelledMsg));
    setupCodeBlockActions(el.messagesList);
    scrollToBottom();

    setThinking(false);
    el.promptInput.focus();
  }

  function updateConversationInList(conv) {
    const convIdx = state.conversations.findIndex((c) => c.id === conv.id);
    if (convIdx !== -1) {
      state.conversations[convIdx] = conv;
    } else {
      state.conversations.unshift(conv);
    }
    renderDrawerConversations();
  }

  function setThinking(active) {
    state.isThinking = active;
    el.thinkingIndicator.style.display = 'none';
    if (active) {
      el.btnSend.classList.add('btn-cancel');
      el.btnSend.disabled = false;
      el.btnSend.title = "Arrêter la réponse (Échap)";
      el.btnSend.setAttribute('aria-label', "Arrêter la réponse");
      el.btnSend.innerHTML = '⏹';
      if (el.inputHintText) {
        el.inputHintText.innerHTML = 'Appuyez sur <strong>Échap</strong> ou le bouton <strong>⏹</strong> pour arrêter la réponse';
      }
      scrollToBottom();
    } else {
      el.btnSend.classList.remove('btn-cancel');
      el.btnSend.disabled = false;
      el.btnSend.title = "Envoyer le message (Entrée)";
      el.btnSend.setAttribute('aria-label', "Envoyer le message");
      el.btnSend.innerHTML = '➤';
      if (el.inputHintText) {
        el.inputHintText.innerHTML = 'Astuce : <strong>Entrée</strong> pour envoyer, <strong>Maj + Entrée</strong> pour saut de ligne';
      }
    }
  }

  // ==========================================================================
  // Settings, Auth & MCP Modal
  // ==========================================================================
  function initSettingsModal() {
    el.btnOpenSettings.addEventListener('click', () => openSettings());
    el.btnOpenSettingsDrawer.addEventListener('click', () => openSettings());
    if (el.btnOpenAuth) {
      el.btnOpenAuth.addEventListener('click', () => openSettings('tab-auth'));
    }
    if (el.btnTopbarMcp) {
      el.btnTopbarMcp.addEventListener('click', () => openSettings('tab-mcp'));
    }
    if (el.btnDrawerMcp) {
      el.btnDrawerMcp.addEventListener('click', () => openSettings('tab-mcp'));
    }
    if (el.btnOpenInventoryDrawer) {
      el.btnOpenInventoryDrawer.addEventListener('click', () => openSettings('tab-inventory'));
    }
    if (el.btnRescanInventory) {
      el.btnRescanInventory.addEventListener('click', rescanInventory);
    }
    if (el.inventorySearch) {
      el.inventorySearch.addEventListener('input', () => {
        renderInventoryTable(el.inventorySearch.value.trim().toLowerCase());
      });
    }
    el.btnCloseModal.addEventListener('click', closeSettings);
    el.settingsModal.addEventListener('click', (e) => {
      if (e.target === el.settingsModal) closeSettings();
    });

    // Tab buttons
    const tabs = el.settingsModal.querySelectorAll('.modal-tab');
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        tabs.forEach((t) => t.classList.remove('active'));
        el.settingsModal.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));

        tab.classList.add('active');
        const targetId = tab.dataset.tab;
        const pane = document.getElementById(targetId);
        if (pane) pane.classList.add('active');
        if (targetId === 'tab-inventory') {
          loadInventory();
        }
      });
    });

    // Save Settings
    el.btnSaveSettings.addEventListener('click', async () => {
      state.settings.model = el.selectModel.value;
      state.settings.effort = el.selectEffort.value;
      state.settings.timeout = parseInt(el.inputTimeout.value || '300', 10);
      if (el.inputPrePrompt) {
        state.settings.prePrompt = el.inputPrePrompt.value.trim();
        localStorage.setItem('chassitant_pre_prompt', state.settings.prePrompt);
        try {
          await apiCall('/api/settings', {
            method: 'POST',
            body: JSON.stringify({
              pre_prompt: state.settings.prePrompt,
              model: state.settings.model,
              effort: state.settings.effort,
            }),
          });
        } catch (e) {
          console.debug('Failed to sync settings to server:', e);
        }
      }

      localStorage.setItem('chassitant_model', state.settings.model);
      localStorage.setItem('chassitant_effort', state.settings.effort);
      localStorage.setItem('chassitant_timeout', state.settings.timeout.toString());

      updateModelBadges();
      closeSettings();
    });

    // Check Auth button
    el.btnCheckAuth.addEventListener('click', async () => {
      el.btnCheckAuth.disabled = true;
      el.btnCheckAuth.innerHTML = '<span>⏳</span><span>Vérification...</span>';
      await refreshAuthStatus();
      el.btnCheckAuth.disabled = false;
      el.btnCheckAuth.innerHTML = '<span>✅</span><span>Vérifier le statut de connexion</span>';
    });

    // Reload Terminal button
    if (el.btnReloadTerminal && el.terminalFrame) {
      el.btnReloadTerminal.addEventListener('click', () => {
        el.terminalFrame.src = 'terminal/?t=' + Date.now();
      });
    }

    // Connect / Reconnect MCP button
    if (el.btnConnectMcp) {
      el.btnConnectMcp.addEventListener('click', handleConnectMcp);
    }
  }

  async function handleConnectMcp() {
    if (!el.btnConnectMcp) return;
    try {
      el.btnConnectMcp.disabled = true;
      if (el.btnConnectMcpText) el.btnConnectMcpText.textContent = 'Connexion en cours...';
      if (el.mcpFeedbackBanner) el.mcpFeedbackBanner.style.display = 'none';

      const customToken = el.inputMcpToken ? el.inputMcpToken.value.trim() : '';
      const customUrl = el.inputMcpUrl ? el.inputMcpUrl.value.trim() : '';

      const payload = {};
      if (customToken) payload.token = customToken;
      if (customUrl) payload.url = customUrl;

      const res = await apiCall('/api/mcp/setup', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      if (el.mcpFeedbackBanner) {
        el.mcpFeedbackBanner.style.display = 'block';
        if (res.success) {
          el.mcpFeedbackBanner.style.background = 'rgba(16, 185, 129, 0.15)';
          el.mcpFeedbackBanner.style.border = '1px solid rgba(16, 185, 129, 0.4)';
          el.mcpFeedbackBanner.style.color = '#34d399';
          el.mcpFeedbackBanner.textContent = '✅ ' + (res.message || 'Serveur MCP Home Assistant connecté avec succès.');
        } else {
          el.mcpFeedbackBanner.style.background = 'rgba(239, 68, 68, 0.15)';
          el.mcpFeedbackBanner.style.border = '1px solid rgba(239, 68, 68, 0.4)';
          el.mcpFeedbackBanner.style.color = '#f87171';
          el.mcpFeedbackBanner.textContent = '❌ ' + (res.message || 'Échec de configuration du serveur MCP.');
        }
      }

      await loadMcpServers();
    } catch (err) {
      if (el.mcpFeedbackBanner) {
        el.mcpFeedbackBanner.style.display = 'block';
        el.mcpFeedbackBanner.style.background = 'rgba(239, 68, 68, 0.15)';
        el.mcpFeedbackBanner.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        el.mcpFeedbackBanner.style.color = '#f87171';
        el.mcpFeedbackBanner.textContent = '❌ Erreur MCP : ' + err.message;
      }
    } finally {
      el.btnConnectMcp.disabled = false;
      if (el.btnConnectMcpText) el.btnConnectMcpText.textContent = 'Connecter / Reconnecter MCP';
    }
  }

  function openSettings(activeTabId = null) {
    el.selectModel.value = state.settings.model;
    el.selectEffort.value = state.settings.effort;
    el.inputTimeout.value = state.settings.timeout;
    if (el.inputPrePrompt) {
      el.inputPrePrompt.value = state.settings.prePrompt || '';
    }

    if (activeTabId) {
      const tabs = el.settingsModal.querySelectorAll('.modal-tab');
      tabs.forEach((t) => t.classList.remove('active'));
      el.settingsModal.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));

      const targetTab = el.settingsModal.querySelector(`.modal-tab[data-tab="${activeTabId}"]`);
      const targetPane = document.getElementById(activeTabId);
      if (targetTab) targetTab.classList.add('active');
      if (targetPane) targetPane.classList.add('active');

      if (activeTabId === 'tab-inventory') {
        loadInventory();
      }
    }

    refreshAuthStatus();
    loadMcpServers();

    el.settingsModal.classList.add('active');
  }

  // ==========================================================================
  // Home Assistant Inventory & Cheat Sheet Management
  // ==========================================================================
  let cachedInventory = null;

  async function loadInventory() {
    if (!el.inventoryTableContainer) return;
    try {
      const res = await apiCall('/api/inventory');
      if (res && res.inventory) {
        cachedInventory = res.inventory;
        updateInventoryCounts(res.counts || {});
        if (el.inventoryLastScan) {
          el.inventoryLastScan.textContent = formatScanDate(res.scanned_at || res.inventory.scanned_at);
        }
        renderInventoryTable(el.inventorySearch ? el.inventorySearch.value.trim().toLowerCase() : '');
      }
    } catch (err) {
      console.warn('loadInventory error:', err);
      if (el.inventoryTableContainer) {
        el.inventoryTableContainer.innerHTML = `<div style="text-align: center; color: var(--accent-danger); padding: 20px;">Erreur de chargement : ${escapeHtml(err.message)}</div>`;
      }
    }
  }

  async function rescanInventory() {
    if (!el.btnRescanInventory) return;
    try {
      el.btnRescanInventory.disabled = true;
      if (el.rescanSpinner) el.rescanSpinner.style.display = 'inline-block';
      if (el.rescanIcon) el.rescanIcon.style.display = 'none';
      if (el.rescanText) el.rescanText.textContent = 'Scan en cours...';

      const res = await apiCall('/api/inventory/scan', {
        method: 'POST',
        body: JSON.stringify({}),
      });

      if (res && res.inventory) {
        cachedInventory = res.inventory;
        updateInventoryCounts(res.counts || {});
        if (el.inventoryLastScan) {
          el.inventoryLastScan.textContent = formatScanDate(res.scanned_at);
        }
        renderInventoryTable(el.inventorySearch ? el.inventorySearch.value.trim().toLowerCase() : '');
      }
    } catch (err) {
      alert(`Erreur lors du scan : ${err.message}`);
    } finally {
      el.btnRescanInventory.disabled = false;
      if (el.rescanSpinner) el.rescanSpinner.style.display = 'none';
      if (el.rescanIcon) el.rescanIcon.style.display = 'inline-block';
      if (el.rescanText) el.rescanText.textContent = 'Actualiser l\'inventaire';
    }
  }

  function updateInventoryCounts(counts) {
    if (el.countWeather) el.countWeather.textContent = counts.weather || 0;
    if (el.countClimates) el.countClimates.textContent = counts.climates || 0;
    if (el.countTemps) el.countTemps.textContent = counts.temperatures || 0;
    if (el.countEnergy) el.countEnergy.textContent = counts.energy_heating || 0;
    if (el.countCovers) el.countCovers.textContent = counts.covers || 0;
    if (el.countLights) el.countLights.textContent = counts.lights || 0;
  }

  function formatScanDate(isoStr) {
    if (!isoStr) return 'Non disponible';
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' (' + d.toLocaleDateString() + ')';
    } catch (_) {
      return isoStr;
    }
  }

  function renderInventoryTable(filterText = '') {
    if (!el.inventoryTableContainer) return;
    if (!cachedInventory) {
      el.inventoryTableContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 20px;">Aucune donnée disponible. Cliquez sur Actualiser.</div>';
      return;
    }

    const sections = [
      { key: 'weather', title: 'Météo', tagClass: 'weather' },
      { key: 'climates', title: 'Chauffage & Clim', tagClass: 'climate' },
      { key: 'temperatures', title: 'Températures', tagClass: 'sensor' },
      { key: 'energy_heating', title: 'Énergie & Conso Chauffage', tagClass: 'sensor' },
      { key: 'covers', title: 'Volets & Stores', tagClass: 'cover' },
      { key: 'lights', title: 'Éclairages', tagClass: 'light' },
    ];

    let rowsHtml = '';
    let totalDisplayed = 0;

    sections.forEach((sec) => {
      const list = cachedInventory[sec.key] || [];
      const filtered = list.filter((item) => {
        if (!filterText) return true;
        const q = filterText.toLowerCase();
        return (
          item.name.toLowerCase().includes(q) ||
          item.entity_id.toLowerCase().includes(q) ||
          (item.state && item.state.toLowerCase().includes(q))
        );
      });

      if (filtered.length > 0) {
        filtered.forEach((item) => {
          totalDisplayed++;
          const stateDisplay = item.unit ? `${item.state} ${item.unit}` : item.state;
          const statusIcon = item.is_active ? '🟢' : '⚪';
          rowsHtml += `
            <tr>
              <td><span class="inv-domain-tag ${sec.tagClass}">${sec.tagClass}</span></td>
              <td><strong>${escapeHtml(item.name)}</strong></td>
              <td>
                <code style="font-size: 11px; background: rgba(0,0,0,0.25); padding: 2px 4px; border-radius: 3px;">${escapeHtml(item.entity_id)}</code>
                <button class="btn-copy-sm" data-copy="${escapeHtml(item.entity_id)}" title="Copier l'identifiant">📋</button>
              </td>
              <td style="white-space: nowrap;">${statusIcon} ${escapeHtml(stateDisplay)}</td>
            </tr>
          `;
        });
      }
    });

    if (totalDisplayed === 0) {
      el.inventoryTableContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 24px;">Aucun équipement ne correspond à "${escapeHtml(filterText)}"</div>`;
      return;
    }

    el.inventoryTableContainer.innerHTML = `
      <table class="inv-table">
        <thead>
          <tr>
            <th style="width: 70px;">Type</th>
            <th>Nom Équipement</th>
            <th>Entity ID</th>
            <th style="width: 130px;">État / Valeur</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;

    // Attach copy listeners
    el.inventoryTableContainer.querySelectorAll('.btn-copy-sm').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const text = btn.dataset.copy;
        if (text) {
          const ok = await copyToClipboard(text);
          const orig = btn.textContent;
          btn.textContent = ok ? '✓' : '✗';
          setTimeout(() => (btn.textContent = orig), 1500);
        }
      });
    });
  }

  function closeSettings() {
    el.settingsModal.classList.remove('active');
  }

  async function refreshAuthStatus() {
    try {
      const data = await apiCall('/api/auth/status');
      state.authStatus = data;

      const isOk = data.authenticated;
      const msg = data.message || (isOk ? 'Connecté' : 'Non connecté');

      // Update Topbar
      if (el.topbarAuthDot) {
        el.topbarAuthDot.className = `status-indicator ${isOk ? 'online' : 'offline'}`;
      }
      if (el.topbarAuthLabel) {
        el.topbarAuthLabel.textContent = isOk ? 'Google Actif' : 'Connexion Google';
      }

      // Update Drawer Pill
      el.drawerAuthDot.className = `status-indicator ${isOk ? 'online' : 'offline'}`;
      el.drawerAuthText.textContent = isOk ? 'Google Actif' : 'Non connecté';

      // Update Modal
      el.authModalBadge.className = `auth-status-tag ${isOk ? 'ok' : 'ko'}`;
      el.authModalBadge.textContent = isOk ? 'Authentifié' : 'Connexion requise';
      el.authModalDesc.textContent = isOk
        ? 'Votre session Google Antigravity est active et enregistrée de façon permanente.'
        : 'Session Google inactive. Suivez les instructions dans le terminal Ingress ci-dessous pour vous connecter.';
    } catch (err) {
      console.error('Failed to check auth:', err);
    }
  }

  async function loadMcpServers() {
    try {
      const data = await apiCall('/api/mcp/list');
      state.mcpServers = data.servers || [];

      const count = state.mcpServers.length;
      const isConnected = count > 0;

      // Topbar button & badge
      if (el.btnTopbarMcp) {
        if (isConnected) {
          el.btnTopbarMcp.classList.add('highlight');
        } else {
          el.btnTopbarMcp.classList.remove('highlight');
        }
      }
      if (el.topbarMcpDot) {
        el.topbarMcpDot.className = `status-indicator ${isConnected ? 'online' : 'offline'}`;
      }
      if (el.topbarMcpText) {
        el.topbarMcpText.textContent = isConnected ? '82 Outils MCP' : 'Connecter MCP';
      }

      // Drawer badge
      if (el.drawerMcpDot) {
        el.drawerMcpDot.className = `status-indicator ${isConnected ? 'online' : 'offline'}`;
      }
      if (el.drawerMcpText) {
        el.drawerMcpText.textContent = isConnected ? 'MCP Actif' : 'MCP Inactif';
      }

      // Modal Status
      if (el.mcpStatusBadge) {
        el.mcpStatusBadge.className = `auth-status-tag ${isConnected ? 'ok' : 'ko'}`;
        el.mcpStatusBadge.textContent = isConnected ? 'Connecté & Opérationnel' : 'Non connecté';
      }
      if (el.mcpToolsCountBadge) {
        el.mcpToolsCountBadge.textContent = isConnected ? `${count} serveur(s) • ~82 outils` : '0 outil actif';
      }
      if (el.mcpStatusDesc) {
        el.mcpStatusDesc.textContent = isConnected
          ? 'Le serveur ha-mcp est opérationnel. Françoise a un accès complet aux outils de contrôle, lecture des états et configuration de Home Assistant.'
          : 'Le serveur MCP n\'est pas encore connecté. Cliquez sur le bouton "Connecter / Reconnecter MCP" pour activer le contrôle de votre domotique.';
      }

      if (!isConnected) {
        if (el.mcpServersList) {
          el.mcpServersList.innerHTML = `
            <div style="color: var(--text-muted); font-size: 12px; padding: 10px 0; text-align: center;">
              ⚠️ Aucun serveur MCP actif. Cliquez sur <strong>Connecter MCP</strong> ci-dessus pour initialiser la liaison.
            </div>
          `;
        }
        return;
      }

      if (el.mcpServersList) {
        el.mcpServersList.innerHTML = state.mcpServers.map((srv) => `
          <div class="mcp-item" style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:var(--bg-secondary); border-radius:var(--radius-sm); border:1px solid var(--border-color);">
            <div class="mcp-item-info">
              <span class="mcp-name" style="font-weight:600; font-size:13px; color:var(--text-primary); display:block;">⚡ ${escapeHtml(srv.name || 'homeassistant')}</span>
              <span class="mcp-desc" style="font-size:11.5px; color:var(--text-muted);">
                ${escapeHtml(srv.command || 'ha-mcp stdio')} • ${escapeHtml(srv.url || 'http://supervisor/core')}
              </span>
            </div>
            <span class="auth-status-tag ok" style="font-size:11px;">~82 Outils Actifs</span>
          </div>
        `).join('');
      }
    } catch (err) {
      console.error('Failed to load MCP servers:', err);
    }
  }

  function updateEffortBadge() {
    if (!el.effortToggleText) return;
    const effortLabels = {
      'low': '⚡ Rapide',
      'medium': '⚖️ Équilibré',
      'high': '🧠 Approfondi',
      'max': '💥 Max',
    };
    const eff = state.settings.effort || 'low';
    el.effortToggleText.textContent = effortLabels[eff] || '⚡ Rapide';
    if (el.selectEffort) el.selectEffort.value = eff;
  }

  function updateModelBadges() {
    const modelLabels = {
      'default': 'Gemini 3.8 Flash',
      'gemini-2.5-flash': 'Gemini 2.5 Flash',
      'gemini-2.5-pro': 'Gemini 2.5 Pro',
      'claude-3-5-sonnet': 'Claude 3.5 Sonnet',
      'claude-3-7-sonnet': 'Claude 3.7 Sonnet',
    };
    const label = modelLabels[state.settings.model] || state.settings.model;
    el.topbarModelText.textContent = label;
    el.activeModelHint.textContent = `Modèle : ${label}`;
    updateEffortBadge();
  }

  // ==========================================================================
  // Event Listeners & Suggestions
  // ==========================================================================
  function initEventListeners() {
    // New Chat buttons
    el.btnNewChat.addEventListener('click', () => createNewConversation('Nouvelle conversation', true));

    // Active title click to rename
    el.activeConvTitle.addEventListener('click', () => {
      if (state.activeConvId && state.activeConversation) {
        promptRenameConversation(state.activeConvId, state.activeConversation.title);
      }
    });

    // Search input
    el.searchInput.addEventListener('input', () => {
      renderDrawerConversations();
    });

    // Prompt input auto-resize & keyboard shortcuts
    el.promptInput.addEventListener('input', () => {
      el.promptInput.style.height = 'auto';
      el.promptInput.style.height = Math.min(el.promptInput.scrollHeight, 180) + 'px';
    });

    el.promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    el.btnSend.addEventListener('click', () => {
      if (state.isThinking) {
        cancelCurrentTurn();
      } else {
        sendMessage();
      }
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.isThinking) {
        e.preventDefault();
        cancelCurrentTurn();
      }
    });

    // Effort quick toggle button
    if (el.btnEffortToggle) {
      el.btnEffortToggle.addEventListener('click', () => {
        const order = ['low', 'medium', 'high'];
        const currentIdx = order.indexOf(state.settings.effort);
        const nextEffort = order[(currentIdx + 1) % order.length];
        state.settings.effort = nextEffort;
        localStorage.setItem('chassitant_effort', nextEffort);
        updateEffortBadge();
      });
    }

    // Context compaction button
    if (el.btnCompactConv) {
      el.btnCompactConv.addEventListener('click', async () => {
        if (!state.activeConvId) {
          alert('Veuillez sélectionner ou démarrer une conversation d\'abord.');
          return;
        }
        const confirmed = confirm('Voulez-vous compacter cette conversation pour alléger l\'historique et accélérer les réponses de Gemini ?');
        if (!confirmed) return;

        const originalText = el.btnCompactConv.textContent;
        el.btnCompactConv.disabled = true;
        el.btnCompactConv.textContent = '⏳';

        try {
          const res = await apiCall(`/api/conversations/${state.activeConvId}/compact`, {
            method: 'POST',
          });
          if (res.success) {
            alert('✅ Contexte de la conversation compacté avec succès ! Les futurs échanges seront beaucoup plus rapides.');
          } else {
            alert('ℹ️ ' + (res.response || 'Compactage effectué.'));
          }
        } catch (err) {
          alert('❌ Erreur lors du compactage : ' + err.message);
        } finally {
          el.btnCompactConv.disabled = false;
          el.btnCompactConv.textContent = originalText;
        }
      });
    }

    // Suggestion chips
    document.querySelectorAll('.suggestion-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const prompt = btn.dataset.prompt;
        if (prompt) {
          el.promptInput.value = prompt;
          sendMessage();
        }
      });
    });

    // Assistant response copy button handler (event delegation)
    el.messagesList.addEventListener('click', async (e) => {
      const btn = e.target.closest('.btn-copy-msg');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();

      const bubble = btn.closest('.message-bubble');
      if (!bubble) return;

      let textToCopy = '';
      const rawHolder = bubble.querySelector('.raw-text-source');
      if (rawHolder && rawHolder.value) {
        textToCopy = rawHolder.value;
      } else {
        const clone = bubble.cloneNode(true);
        const unwanted = clone.querySelectorAll(
          '.reasoning-details, .message-footer, .message-meta, .message-actions, .raw-text-source, script, style'
        );
        unwanted.forEach((n) => n.remove());
        textToCopy = clone.innerText.trim();
      }

      if (!textToCopy) return;

      const originalHtml = btn.innerHTML;
      const ok = await copyToClipboard(textToCopy);

      if (ok) {
        btn.classList.add('copied');
        btn.innerHTML = `
          <svg class="copy-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span class="copy-text">Copié !</span>
        `;
        setTimeout(() => {
          btn.classList.remove('copied');
          btn.innerHTML = originalHtml;
        }, 2000);
      } else {
        const copyText = btn.querySelector('.copy-text');
        if (copyText) copyText.textContent = 'Erreur';
        setTimeout(() => {
          btn.innerHTML = originalHtml;
        }, 2000);
      }
    });
  }

  // ==========================================================================
  // Helpers
  // ==========================================================================
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatTime(timestamp) {
    try {
      const date = new Date(timestamp * 1000);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return '';
    }
  }

  // ==========================================================================
  // Initialization
  // ==========================================================================
  async function init() {
    initDrawer();
    initSettingsModal();
    initEventListeners();
    updateModelBadges();

    try {
      const serverSettings = await apiCall('/api/settings');
      if (serverSettings && serverSettings.pre_prompt && !localStorage.getItem('chassitant_pre_prompt')) {
        state.settings.prePrompt = serverSettings.pre_prompt;
      }
    } catch (e) {
      // Optional settings fetch
    }

    await loadConversations();
    refreshAuthStatus();
    loadMcpServers();
  }

  // Start app when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
