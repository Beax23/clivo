/* =========================================================================
   REUNIÕES — página registrada no shell ClivoPages
   ATENÇÃO: dados mockados para visualização. Substituir quando o back existir.
   ========================================================================= */

(function() {
    'use strict';

    // =====================================================================
    // HELPERS
    // =====================================================================

    function showToast(msg, type) {
        if (typeof window.clivoShowToast === 'function') {
            window.clivoShowToast(msg, type);
        }
    }

    function escapeHtml(s) {
        if (s === null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function refreshIcons() {
        if (typeof window.clivoRefreshIcons === 'function') {
            window.clivoRefreshIcons();
        }
    }

    function formatDateTime(iso) {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            return d.toLocaleString('pt-BR', {
                day: '2-digit', month: 'short',
                hour: '2-digit', minute: '2-digit',
            });
        } catch (e) { return '—'; }
    }

    function formatDuration(seconds) {
        if (!seconds && seconds !== 0) return '—';
        const total = parseInt(seconds, 10);
        if (isNaN(total) || total === 0) return '—';
        const min = Math.floor(total / 60);
        return min + ' min';
    }

    function formatGroupLabel(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        const diff = Math.round((today - target) / (1000 * 60 * 60 * 24));
        if (diff === 0) return 'HOJE';
        if (diff === 1) return 'ONTEM';
        if (diff < 7) return d.toLocaleDateString('pt-BR', { weekday: 'long' }).toUpperCase();
        return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '').toUpperCase();
    }

    // =====================================================================
    // ESTADO
    // =====================================================================

    let meetingsCache = [];
    let currentMeeting = null;
    let notesCache = [];

    // =====================================================================
    // MOCKS
    // =====================================================================

    const MOCK_MEETINGS = [
        {
            id: 'm1',
            title: 'Reunião de briefing',
            client_name: 'Casa Almeida',
            person_name: 'Maria Almeida',
            scheduled_at: new Date(new Date().setHours(10, 30, 0, 0)).toISOString(),
            duration_seconds: 45 * 60,
            status: 'completed',
            has_audio: true,
            has_transcript: true,
            transcript: [
                { time: '10:32', text: 'Eu acho que podemos manter a cozinha mais integrada à área social.' },
                { time: '10:34', text: 'Eu gostaria que tivesse mais luz natural, principalmente à tarde.' },
                { time: '10:36', text: 'Nesse caso precisamos avaliar a abertura. Talvez uma janela maior na parede leste.' },
                { time: '10:40', text: 'E a bancada? Dá para manter o tamanho atual?' },
                { time: '10:42', text: 'Vou verificar. Acho que dá para ganhar uns 30cm se tirarmos aquele armário.' },
            ],
            audios: [{ name: 'reuniao-briefing.m4a', size: '18 MB' }],
            notes: [
                'Cliente prefere madeira clara.',
                'Rever iluminação da área social.',
                'Confirmar medida da bancada.',
            ],
            files: [{ name: 'briefing-casa.pdf', size: '2 MB' }],
        },
        {
            id: 'm2',
            title: 'Apresentação inicial',
            client_name: 'Apartamento Silva',
            person_name: 'Carlos Silva',
            scheduled_at: new Date(new Date().setHours(16, 0, 0, 0)).toISOString(),
            duration_seconds: 32 * 60,
            status: 'completed',
            has_audio: true,
            has_transcript: true,
            transcript: [
                { time: '16:02', text: 'Esse é o conceito inicial. Paleta neutra, madeira natural, muito branco.' },
                { time: '16:05', text: 'Gostei. Acho que combina com o que a gente imaginava.' },
                { time: '16:08', text: 'Ótimo. Vou preparar o próximo estudo com mobiliário.' },
            ],
            audios: [{ name: 'apresentacao-inicial.m4a', size: '12 MB' }],
            notes: [],
            files: [{ name: 'conceito-inicial.pdf', size: '5 MB' }],
        },
        {
            id: 'm3',
            title: 'Reunião de alinhamento',
            client_name: 'Casa Ferreira',
            person_name: 'Roberto Ferreira',
            scheduled_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
            duration_seconds: 51 * 60,
            status: 'scheduled',
            has_audio: true,
            has_transcript: false,
            transcript: [],
            audios: [{ name: 'alinhamento-ferreira.m4a', size: '22 MB' }],
            notes: [],
            files: [],
        },
        {
            id: 'm4',
            title: 'Revisão de orçamento',
            client_name: 'Casa Almeida',
            person_name: 'Maria Almeida',
            scheduled_at: new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString(),
            duration_seconds: 28 * 60,
            status: 'completed',
            has_audio: false,
            has_transcript: true,
            transcript: [
                { time: '14:00', text: 'O orçamento das esquadrias subiu um pouco.' },
                { time: '14:02', text: 'Dá para reduzir? Precisamos ficar dentro do previsto.' },
                { time: '14:05', text: 'Vou ver alternativas com fornecedores.' },
            ],
            audios: [],
            notes: [],
            files: [],
        },
        {
            id: 'm5',
            title: 'Alinhamento com fornecedor',
            client_name: 'Casa Silva',
            person_name: 'Ana',
            scheduled_at: new Date(Date.now() - 5 * 24 * 3600 * 1000).toISOString(),
            duration_seconds: 22 * 60,
            status: 'completed',
            has_audio: false,
            has_transcript: false,
            transcript: [],
            audios: [],
            notes: [],
            files: [],
        },
    ];

    // =====================================================================
    // LISTA
    // =====================================================================

    function loadMeetings() {
        meetingsCache = MOCK_MEETINGS.slice();
        renderList();
    }

    function getFilteredMeetings() {
        const searchInput = document.getElementById('rnSearchInput');
        const query = (searchInput && searchInput.value || '').trim().toLowerCase();

        const reviewSelect = document.getElementById('rnReviewFilter');
        const reviewFilter = reviewSelect ? reviewSelect.value : '';

        let items = meetingsCache.slice();

        if (reviewFilter) {
            items = items.filter(function(m) {
                if (reviewFilter === 'transcribed') return m.has_transcript;
                if (reviewFilter === 'to_review') return m.has_transcript && !(m.notes && m.notes.length);
                if (reviewFilter === 'reviewed') return !!(m.notes && m.notes.length);
                return true;
            });
        }

        if (query) {
            items = items.filter(function(m) {
                const title = (m.title || '').toLowerCase();
                const person = (m.person_name || '').toLowerCase();
                const client = (m.client_name || '').toLowerCase();
                return title.indexOf(query) !== -1 ||
                       person.indexOf(query) !== -1 ||
                       client.indexOf(query) !== -1;
            });
        }

        items.sort(function(a, b) {
            return new Date(b.scheduled_at) - new Date(a.scheduled_at);
        });

        return items;
    }

    function groupByDay(items) {
        const groups = [];
        let current = null;
        items.forEach(function(m) {
            const label = formatGroupLabel(m.scheduled_at);
            if (!current || current.label !== label) {
                current = { label: label, items: [] };
                groups.push(current);
            }
            current.items.push(m);
        });
        return groups;
    }

    function renderList() {
        const listEl = document.getElementById('rnList');
        if (!listEl) return;

        const items = getFilteredMeetings();

        if (!items.length) {
            listEl.innerHTML =
                '<div class="rn-list-empty">' +
                    '<i data-lucide="mic-off"></i>' +
                    '<p>Nenhuma reunião encontrada</p>' +
                '</div>';
            refreshIcons();
            return;
        }

        const groups = groupByDay(items);
        let html = '';

        groups.forEach(function(group) {
            html += '<div class="rn-group">';
            html += '<div class="rn-group-label">' + escapeHtml(group.label) + '</div>';

            group.items.forEach(function(m) {
                const isSelected = currentMeeting && currentMeeting.id === m.id;
                const duration = formatDuration(m.duration_seconds);
                const status = m.status || 'scheduled';
                const audioIcon = m.has_audio ? 'volume-2' : 'volume-x';
                const audioClass = m.has_audio ? ' has-audio' : '';
                const personName = m.person_name || m.client_name || 'Sem pessoa';

                html +=
                    '<div class="rn-item' + (isSelected ? ' is-selected' : '') + '" data-meeting-id="' + escapeHtml(m.id) + '">' +
                        '<div class="rn-item-status">' +
                            '<span class="rn-item-status-dot ' + escapeHtml(status) + '"></span>' +
                        '</div>' +
                        '<div class="rn-item-info">' +
                            '<div class="rn-item-title">' + escapeHtml(m.title) + '</div>' +
                            '<div class="rn-item-client">' + escapeHtml(personName) + '</div>' +
                            '<div class="rn-item-duration">' +
                                '<i data-lucide="clock"></i>' +
                                '<span>' + escapeHtml(duration) + '</span>' +
                            '</div>' +
                        '</div>' +
                        '<div class="rn-item-audio' + audioClass + '">' +
                            '<i data-lucide="' + audioIcon + '"></i>' +
                        '</div>' +
                    '</div>';
            });

            html += '</div>';
        });

        listEl.innerHTML = html;
        refreshIcons();

        listEl.querySelectorAll('.rn-item').forEach(function(el) {
            el.addEventListener('click', function() {
                const id = this.dataset.meetingId;
                if (id) openMeeting(id);
            });
        });
    }

    // =====================================================================
    // MESA DE REVISÃO
    // =====================================================================

    function openMeeting(id) {
        const meeting = meetingsCache.find(function(m) { return m.id === id; });
        if (!meeting) return;

        currentMeeting = meeting;
        notesCache = (meeting.notes || []).slice();

        const review = document.getElementById('rnReview');
        const empty = document.getElementById('rnReviewEmpty');
        if (review) review.classList.remove('hidden');
        if (empty) empty.classList.add('hidden');

        renderReview();
        renderList();
    }

    function renderReview() {
        if (!currentMeeting) return;
        const m = currentMeeting;

        const setText = function(id, val) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        // Título: "Reunião · Cliente"
        const titleBase = m.title || 'Reunião';
        const titleFull = m.client_name ? (titleBase + ' · ' + m.client_name) : titleBase;
        setText('rnMeetingTitle', titleFull);

        setText('rnMeetingDate', formatDateTime(m.scheduled_at));
        setText('rnMeetingDuration', formatDuration(m.duration_seconds));

        // KPIs
        const audioCount = (m.audios || []).length;
        const fileCount = (m.files || []).length;
        const noteCount = (notesCache || []).length;

        setText('rnKpiAudios', audioCount);
        setText('rnKpiFiles', fileCount);
        setText('rnKpiNotes', noteCount);

        // Status badge
        const statusEl = document.getElementById('rnMeetingStatus');
        if (statusEl) {
            const status = m.status || 'scheduled';
            statusEl.className = 'rn-status-badge ' + status;
            statusEl.textContent =
                status === 'completed' ? 'Concluída' :
                status === 'cancelled' ? 'Cancelada' :
                'Agendada';
        }

        // Áudio
        const audioEmpty = document.getElementById('rnAudioEmpty');
        const audioPlayer = document.getElementById('rnAudioPlayer');
        const audioFileEl = document.getElementById('rnAudioFile');
        const audioCountEl = document.getElementById('rnAudioCount');
        const audioList = document.getElementById('rnAudioList');
        const audioListItems = document.getElementById('rnAudioListItems');

        const hasAudio = m.has_audio && (m.audios || []).length > 0;

        if (hasAudio) {
            const first = m.audios[0];
            if (audioEmpty) audioEmpty.classList.add('hidden');
            if (audioPlayer) audioPlayer.classList.remove('hidden');
            if (audioFileEl) audioFileEl.textContent = first.name;
            if (audioCountEl) audioCountEl.textContent = String(m.audios.length);

            if (audioListItems) {
                let html = '';
                m.audios.forEach(function(a, i) {
                    html +=
                        '<li' + (i === 0 ? ' class="is-current"' : '') + ' data-audio-idx="' + i + '">' +
                            '<i data-lucide="' + (i === 0 ? 'volume-2' : 'volume-1') + '"></i>' +
                            '<span class="rn-audio-list-name">' + escapeHtml(a.name) + '</span>' +
                            (a.size ? '<span class="rn-audio-list-size">' + escapeHtml(a.size) + '</span>' : '') +
                        '</li>';
                });
                audioListItems.innerHTML = html;
            }
            if (audioList) audioList.classList.add('hidden');
        } else {
            if (audioEmpty) audioEmpty.classList.remove('hidden');
            if (audioPlayer) audioPlayer.classList.add('hidden');
            if (audioList) audioList.classList.add('hidden');
        }

        // Transcrição
        const transcriptBody = document.getElementById('rnTranscriptBody');
        if (transcriptBody) {
            if (m.transcript && m.transcript.length) {
                let html = '<div class="rn-transcript">';
                m.transcript.forEach(function(line) {
                    html +=
                        '<div class="rn-transcript-block">' +
                            '<span class="rn-transcript-time">' + escapeHtml(line.time) + '</span>' +
                            '<p class="rn-transcript-text">' + escapeHtml(line.text) + '</p>' +
                        '</div>';
                });
                html += '</div>';
                transcriptBody.innerHTML = html;
            } else {
                transcriptBody.innerHTML = '<div class="rn-empty-inline"><p>Sem transcrição ainda.</p></div>';
            }
        }

        // Notas
        renderNotes();

        refreshIcons();
    }

    function renderNotes() {
        const notesList = document.getElementById('rnNotesList');
        if (!notesList) return;

        if (!notesCache || !notesCache.length) {
            notesList.innerHTML = '<li class="rn-empty-inline"><p>Nenhuma anotação.</p></li>';
            refreshIcons();
            return;
        }

        let html = '';
        notesCache.forEach(function(n) {
            html += '<li>' + escapeHtml(n) + '</li>';
        });
        notesList.innerHTML = html;
        refreshIcons();
    }

    // =====================================================================
    // ÁUDIO — controles
    // =====================================================================

    function setupAudioControls() {
        const toggle = document.getElementById('rnAudioListToggle');
        const list = document.getElementById('rnAudioList');
        const playBtn = document.getElementById('rnAudioPlayBtn');
        const track = document.querySelector('.rn-audio-track');

        if (toggle && list) {
            toggle.addEventListener('click', function(e) {
                e.stopPropagation();
                const isHidden = list.classList.toggle('hidden');
                toggle.classList.toggle('open', !isHidden);
            });
        }

        if (playBtn) {
            playBtn.addEventListener('click', function() {
                showToast('Reprodução de áudio — em desenvolvimento', 'info');
            });
        }

        if (track) {
            track.addEventListener('click', function(e) {
                const rect = this.getBoundingClientRect();
                const pct = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
                const progress = document.getElementById('rnAudioProgress');
                if (progress) progress.style.width = pct + '%';
            });
        }

        document.addEventListener('click', function(e) {
            const item = e.target.closest('#rnAudioListItems li');
            if (!item) return;
            const idx = parseInt(item.dataset.audioIdx, 10);
            if (isNaN(idx) || !currentMeeting || !currentMeeting.audios) return;
            const audio = currentMeeting.audios[idx];
            if (!audio) return;

            const nameEl = document.getElementById('rnAudioFile');
            if (nameEl) nameEl.textContent = audio.name;

            document.querySelectorAll('#rnAudioListItems li').forEach(function(li) {
                li.classList.remove('is-current');
            });
            item.classList.add('is-current');

            refreshIcons();
        });
    }

    // =====================================================================
    // NOTAS — form
    // =====================================================================

    function setupNoteForm() {
        const input = document.getElementById('rnNoteInput');
        const btn = document.getElementById('rnNoteSubmitBtn');
        const form = document.getElementById('rnNoteForm');

        if (!input || !btn || !form) return;

        input.addEventListener('input', function() {
            btn.disabled = !this.value.trim();
        });

        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const value = input.value.trim();
            if (!value) return;

            notesCache.push(value);
            input.value = '';
            btn.disabled = true;

            if (currentMeeting) {
                currentMeeting.notes = notesCache.slice();
            }

            renderNotes();

            const kpiNotes = document.getElementById('rnKpiNotes');
            if (kpiNotes) kpiNotes.textContent = notesCache.length;
        });
    }

    // =====================================================================
    // FILTROS
    // =====================================================================

    function setupFilters() {
        const search = document.getElementById('rnSearchInput');
        if (search) search.addEventListener('input', renderList);

        const period = document.getElementById('rnPeriodFilter');
        if (period) period.addEventListener('change', renderList);

        const review = document.getElementById('rnReviewFilter');
        if (review) review.addEventListener('change', renderList);
    }

    // =====================================================================
    // BOTÕES
    // =====================================================================

    function setupButtons() {
        const calBtn = document.getElementById('rnCalendarBtn');
        if (calBtn) {
            calBtn.addEventListener('click', function() {
                showToast('Google Calendar — em desenvolvimento', 'info');
            });
        }

        const addHeader = document.getElementById('rnAddAudioBtnHeader');
        if (addHeader) {
            addHeader.addEventListener('click', function() {
                showToast('Adicionar conteúdo — em desenvolvimento', 'info');
            });
        }

        const headerAddBtn = document.getElementById('rnHeaderAddBtn');
        if (headerAddBtn) {
            headerAddBtn.addEventListener('click', function() {
                showToast('Adicionar conteúdo — em desenvolvimento', 'info');
            });
        }

        const addNoteBtn = document.getElementById('rnAddNoteBtn');
        if (addNoteBtn) {
            addNoteBtn.addEventListener('click', function() {
                const input = document.getElementById('rnNoteInput');
                if (input) input.focus();
            });
        }
    }

    // =====================================================================
    // MOUNT / UNMOUNT
    // =====================================================================

    function mount() {
        loadMeetings();
        setupFilters();
        setupButtons();
        setupAudioControls();
        setupNoteForm();

        const first = getFilteredMeetings()[0];
        if (first) openMeeting(first.id);

        refreshIcons();
    }

    function unmount() {}

    window.ClivoPages = window.ClivoPages || {};
    window.ClivoPages.reunioes = {
        mount: mount,
        unmount: unmount,
    };
})();