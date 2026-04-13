var VideoModal = (function() {
    'use strict';
    
    var config = {
        package_name: 'anime_downloader',
        sub: 'ohli24'
    };
    
    var videoPlayer = null;  // Video.js instance
    var artPlayer = null;    // Artplayer instance
    var plyrPlayer = null;   // Plyr instance
    var currentPlayer = 'videojs';  // 'videojs', 'artplayer', 'plyr'
    var playlist = [];
    var currentPlaylistIndex = 0;
    var currentPlayingPath = '';
    var currentStreamUrl = '';
    var currentSourceOptions = {};
    var isVideoZoomed = false;
    var SUBTITLE_SIZE_KEY = 'anime_downloader_art_subtitle_size';
    var SUBTITLE_BG_KEY = 'anime_downloader_art_subtitle_bg';

    function getSavedSubtitleSize() {
        var size = parseInt(localStorage.getItem(SUBTITLE_SIZE_KEY) || '18', 10);
        if (isNaN(size) || size < 12 || size > 36) return 18;
        return size;
    }

    function getSavedSubtitleBg() {
        var mode = localStorage.getItem(SUBTITLE_BG_KEY) || 'dark';
        return (mode === 'clear') ? 'clear' : 'dark';
    }

    function getSubtitleStyle(size, bgMode) {
        return {
            color: '#FFFFFF',
            'font-size': size + 'px',
            'background-color': (bgMode === 'clear') ? 'transparent' : 'rgba(0, 0, 0, 0.45)'
        };
    }

    function detectSourceType(url, explicitType) {
        if (explicitType) return explicitType;
        if (!url) return 'video/mp4';
        var u = String(url).toLowerCase();
        if (u.indexOf('.m3u8') >= 0 || u.indexOf('application/x-mpegurl') >= 0) {
            return 'application/x-mpegURL';
        }
        return 'video/mp4';
    }

    function isHttpLikeUrl(value) {
        if (!value) return false;
        var v = String(value);
        return /^https?:\/\//i.test(v) || v.indexOf('/ajax/' + config.sub + '/proxy_remote_media') >= 0;
    }

    function toAbsoluteUrl(url) {
        if (!url) return '';
        if (/^https?:\/\//i.test(url)) return url;
        if (url.charAt(0) === '/') return window.location.origin + url;
        return window.location.origin + '/' + url;
    }

    function clearSubtitleTracks() {
        if (!videoPlayer) return;
        try {
            var trackEls = videoPlayer.remoteTextTrackEls ? videoPlayer.remoteTextTrackEls() : null;
            if (trackEls && trackEls.length) {
                for (var i = trackEls.length - 1; i >= 0; i--) {
                    videoPlayer.removeRemoteTextTrack(trackEls[i]);
                }
            }
        } catch (e) {}
    }

    function applySubtitleTrack(subtitleUrl) {
        clearSubtitleTracks();
        if (!videoPlayer || !subtitleUrl) return;
        try {
            var trackRef = videoPlayer.addRemoteTextTrack({
                kind: 'subtitles',
                src: subtitleUrl,
                srclang: 'ko',
                label: 'Korean',
                "default": true
            }, false);
            if (trackRef && trackRef.track) {
                trackRef.track.mode = 'showing';
            }
        } catch (e) {
            console.warn('[VideoModal] subtitle attach failed:', e);
        }
    }
    
    /**
     * Initialize the video modal
     */
    function init(options) {
        config = Object.assign(config, options || {});
        
        // Load saved player preference
        var savedPlayer = localStorage.getItem('anime_downloader_preferred_player');
        if (savedPlayer && ['videojs', 'artplayer', 'plyr'].indexOf(savedPlayer) >= 0) {
            currentPlayer = savedPlayer;
            $('#player-select').val(currentPlayer);
        }
        
        bindEvents();
        console.log('[VideoModal] Initialized with player:', currentPlayer);
    }
    
    /**
     * Bind all event handlers
     */
    function bindEvents() {
        // Player selector change
        $('#player-select').off('change').on('change', function() {
            var newPlayer = $(this).val();
            if (newPlayer !== currentPlayer) {
                switchPlayer(newPlayer);
            }
        });
        
        // Dropdown episode selection
        $('#episode-dropdown').off('change').on('change', function() {
            var index = parseInt($(this).val());
            if (index !== currentPlaylistIndex && index >= 0 && index < playlist.length) {
                currentPlaylistIndex = index;
                playVideoAtIndex(index);
            }
        });
        
        // Video zoom button
        $('#btn-video-zoom').off('click').on('click', function() {
            isVideoZoomed = !isVideoZoomed;
            if (isVideoZoomed) {
                $('#video-player, #plyr-player').addClass('vjs-zoomed');
                $('#artplayer-container').addClass('art-zoomed');
                $(this).addClass('active').find('i').removeClass('fa-expand').addClass('fa-compress');
            } else {
                $('#video-player, #plyr-player').removeClass('vjs-zoomed');
                $('#artplayer-container').removeClass('art-zoomed');
                $(this).removeClass('active').find('i').removeClass('fa-compress').addClass('fa-expand');
            }
        });
        
        // Modal events
        $('#videoModal').off('show.bs.modal').on('show.bs.modal', function() {
            $('body').addClass('modal-video-open');
            if (currentStreamUrl) {
                tryAutoPlay(140);
            }
        });
        
        $('#videoModal').off('hide.bs.modal').on('hide.bs.modal', function() {
            pauseAllPlayers();
        });
        
        $('#videoModal').off('hidden.bs.modal').on('hidden.bs.modal', function() {
            $('body').removeClass('modal-video-open');
            if (isVideoZoomed) {
                isVideoZoomed = false;
                $('#video-player, #plyr-player').removeClass('vjs-zoomed');
                $('#artplayer-container').removeClass('art-zoomed');
                $('#btn-video-zoom').removeClass('active').find('i').removeClass('fa-compress').addClass('fa-expand');
            }
        });
    }
    
    /**
     * Switch between players
     */
    function switchPlayer(newPlayer) {
        pauseAllPlayers();
        
        currentPlayer = newPlayer;
        localStorage.setItem('anime_downloader_preferred_player', newPlayer);
        
        // Hide all player containers
        $('#videojs-container').hide();
        $('#artplayer-container').hide();
        $('#plyr-container').hide();
        
        // Show selected player and reinitialize with current URL
        if (currentStreamUrl) {
            initPlayerWithUrl(currentStreamUrl, currentSourceOptions);
            tryAutoPlay(100);
        }
        
        console.log('[VideoModal] Switched to:', newPlayer);
    }
    
    /**
     * Pause all players
     */
    function pauseAllPlayers() {
        try {
            if (videoPlayer) videoPlayer.pause();
        } catch(e) {}
        try {
            if (artPlayer) artPlayer.pause();
        } catch(e) {}
        try {
            if (plyrPlayer) plyrPlayer.pause();
        } catch(e) {}
    }

    function tryAutoPlay(delayMs) {
        var delay = (typeof delayMs === 'number') ? delayMs : 120;
        setTimeout(function() {
            try {
                if (currentPlayer === 'videojs' && videoPlayer) {
                    videoPlayer.play();
                } else if (currentPlayer === 'artplayer' && artPlayer) {
                    if (typeof artPlayer.play === 'function') {
                        artPlayer.play();
                    }
                } else if (currentPlayer === 'plyr' && plyrPlayer) {
                    plyrPlayer.play();
                }
            } catch (e) {
                console.debug('[VideoModal] autoplay blocked:', e);
            }
        }, delay);
    }

    function attachAutoplayRetries() {
        tryAutoPlay(120);
    }
    
    /**
     * Initialize player with URL based on current player selection
     */
    function initPlayerWithUrl(streamUrl, options) {
        options = options || {};
        currentStreamUrl = streamUrl;
        currentSourceOptions = Object.assign({}, options);
        
        if (currentPlayer === 'videojs') {
            initVideoJS(streamUrl, options);
        } else if (currentPlayer === 'artplayer') {
            initArtplayer(streamUrl, options);
        } else if (currentPlayer === 'plyr') {
            initPlyr(streamUrl, options);
        }
    }
    
    /**
     * Initialize Video.js player
     */
    function initVideoJS(streamUrl, options) {
        options = options || {};
        // Hide other containers
        $('#artplayer-container').hide();
        $('#plyr-container').hide();
        $('#videojs-container').show();
        
        if (!videoPlayer) {
            videoPlayer = videojs('video-player', {
                controls: true,
                autoplay: false,
                preload: 'auto',
                fluid: true,
                playbackRates: [0.5, 1, 1.5, 2],
                controlBar: {
                    skipButtons: { forward: 10, backward: 10 }
                }
            });
            
            videoPlayer.on('ended', handleVideoEnded);
            videoPlayer.on('loadedmetadata', attachAutoplayRetries);
            videoPlayer.on('canplay', attachAutoplayRetries);
        }
        
        var sourceType = detectSourceType(streamUrl, options.source_type);
        videoPlayer.src({ type: sourceType, src: streamUrl });
        applySubtitleTrack(options.subtitle_url || '');
    }
    
    /**
     * Initialize Artplayer
     */
    function initArtplayer(streamUrl, options) {
        options = options || {};
        // Hide other containers
        $('#videojs-container').hide();
        $('#plyr-container').hide();
        $('#artplayer-container').show().empty();
        
        if (artPlayer) {
            artPlayer.destroy();
            artPlayer = null;
        }
        
        var artConfig = {
            container: '#artplayer-container',
            url: streamUrl,
            autoplay: false,
            pip: true,
            screenshot: true,
            setting: true,
            subtitleOffset: true,
            playbackRate: true,
            aspectRatio: true,
            fullscreen: true,
            fullscreenWeb: true,
            moreVideoAttr: {
                crossorigin: 'anonymous'
            },
            theme: '#3b82f6'
        };
        var savedSubtitleSize = getSavedSubtitleSize();
        var savedSubtitleBg = getSavedSubtitleBg();
        if (options.subtitle_url) {
            artConfig.subtitle = {
                url: options.subtitle_url,
                type: 'vtt',
                encoding: 'utf-8',
                escape: false,
                style: getSubtitleStyle(savedSubtitleSize, savedSubtitleBg)
            };
        }

        artPlayer = new Artplayer(artConfig);
        
        artPlayer.on('video:ended', handleVideoEnded);
        artPlayer.on('ready', attachAutoplayRetries);
        artPlayer.on('ready', function() {
            if (!artPlayer || !artPlayer.setting || typeof artPlayer.setting.add !== 'function') return;
            var sizes = [14, 16, 18, 20, 22, 24, 28];
            artPlayer.setting.add({
                html: '자막 크기',
                width: 180,
                tooltip: savedSubtitleSize + 'px',
                selector: sizes.map(function(size) {
                    return {
                        html: size + 'px',
                        value: size,
                        default: size === savedSubtitleSize,
                    };
                }),
                onSelect: function(item) {
                    var size = parseInt(item.value, 10);
                    if (!isNaN(size)) {
                        localStorage.setItem(SUBTITLE_SIZE_KEY, String(size));
                        if (artPlayer && artPlayer.subtitle && typeof artPlayer.subtitle.style === 'function') {
                            artPlayer.subtitle.style(getSubtitleStyle(size, getSavedSubtitleBg()));
                        }
                    }
                    return item.html;
                },
            });

            artPlayer.setting.add({
                html: '자막 배경',
                width: 180,
                tooltip: (savedSubtitleBg === 'clear') ? '글자만' : '검은 배경',
                selector: [
                    { html: '검은 배경', value: 'dark', default: savedSubtitleBg === 'dark' },
                    { html: '글자만', value: 'clear', default: savedSubtitleBg === 'clear' },
                ],
                onSelect: function(item) {
                    var mode = (item.value === 'clear') ? 'clear' : 'dark';
                    localStorage.setItem(SUBTITLE_BG_KEY, mode);
                    if (artPlayer && artPlayer.subtitle && typeof artPlayer.subtitle.style === 'function') {
                        artPlayer.subtitle.style(getSubtitleStyle(getSavedSubtitleSize(), mode));
                    }
                    return item.html;
                },
            });
        });
    }
    
    /**
     * Initialize Plyr player
     */
    function initPlyr(streamUrl) {
        // Hide other containers
        $('#videojs-container').hide();
        $('#artplayer-container').hide();
        $('#plyr-container').show();
        
        // Set source
        $('#plyr-player').attr('src', streamUrl);
        $('#plyr-player').prop('autoplay', false);
        
        if (!plyrPlayer) {
            plyrPlayer = new Plyr('#plyr-player', {
                controls: ['play-large', 'play', 'progress', 'current-time', 'mute', 'volume', 'settings', 'pip', 'fullscreen'],
                settings: ['quality', 'speed'],
                speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] }
            });
            
            plyrPlayer.on('ended', handleVideoEnded);
            plyrPlayer.on('loadedmetadata', attachAutoplayRetries);
            plyrPlayer.on('canplay', attachAutoplayRetries);
        } else {
            plyrPlayer.source = {
                type: 'video',
                sources: [{ src: streamUrl, type: 'video/mp4' }]
            };
        }
    }
    
    /**
     * Handle video ended event (auto-next)
     */
    function handleVideoEnded() {
        var autoNextEnabled = $('#auto-next-checkbox').is(':checked');
        if (autoNextEnabled && currentPlaylistIndex < playlist.length - 1) {
            currentPlaylistIndex++;
            playVideoAtIndex(currentPlaylistIndex);
        }
    }
    
    /**
     * Play video at specific playlist index
     */
    function playVideoAtIndex(index) {
        if (index < 0 || index >= playlist.length) return;
        currentPlaylistIndex = index;
        var item = playlist[index];
        var streamUrl = item.stream_url
            ? item.stream_url
            : ('/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(item.path));
        var sourceType = detectSourceType(streamUrl, item.source_type);
        
        initPlayerWithUrl(streamUrl, {
            source_type: sourceType,
            subtitle_url: item.subtitle_url || ''
        });
        
        tryAutoPlay(100);
        
        updatePlaylistUI();
    }
    
    /**
     * Open modal with a file path (fetches playlist from server)
     */
    function openWithPath(filePath) {
        $.ajax({
            url: '/' + config.package_name + '/ajax/' + config.sub + '/get_playlist?path=' + encodeURIComponent(filePath),
            type: 'GET',
            dataType: 'json',
            success: function(data) {
                playlist = data.playlist || [];
                currentPlaylistIndex = data.current_index || 0;
                currentPlayingPath = filePath;
                if (playlist.length === 0) {
                    playlist = [{ name: filePath.split('/').pop(), path: filePath }];
                    currentPlaylistIndex = 0;
                }
                $('#videoModal').modal('show');
                playVideoAtIndex(currentPlaylistIndex);
            },
            error: function() {
                playlist = [{ name: filePath.split('/').pop(), path: filePath }];
                currentPlaylistIndex = 0;
                $('#videoModal').modal('show');
                playVideoAtIndex(currentPlaylistIndex);
            }
        });
    }
    
    /**
     * Open modal with a direct stream URL
     */
    function openWithUrl(streamUrl, title) {
        var options = arguments.length > 2 ? arguments[2] : {};
        playlist = [{
            name: title || 'Video',
            path: options.path || streamUrl,
            stream_url: streamUrl,
            subtitle_url: options.subtitle_url || '',
            source_type: detectSourceType(streamUrl, options.source_type),
            is_remote: options.is_remote === true
        }];
        currentPlaylistIndex = 0;
        initPlayerWithUrl(streamUrl, {
            source_type: detectSourceType(streamUrl, options.source_type),
            subtitle_url: options.subtitle_url || ''
        });
        updatePlaylistUI();
        $('#videoModal').modal('show');
        tryAutoPlay(80);
    }
    
    /**
     * Open modal with a playlist array
     */
    function openWithPlaylist(playlistData, startIndex) {
        playlist = playlistData || [];
        currentPlaylistIndex = startIndex || 0;
        if (playlist.length > 0) {
            $('#videoModal').modal('show');
            playVideoAtIndex(currentPlaylistIndex);
        }
    }
    
    /**
     * Update playlist UI (dropdown, external player buttons)
     */
    function updatePlaylistUI() {
        if (!playlist || playlist.length === 0) return;
        
        var currentFile = playlist[currentPlaylistIndex];
        
        // Update dropdown
        var $dropdown = $('#episode-dropdown');
        if ($dropdown.find('option').length !== playlist.length) {
            var optionsHtml = '';
            for (var i = 0; i < playlist.length; i++) {
                optionsHtml += '<option value="' + i + '">' + playlist[i].name + '</option>';
            }
            $dropdown.html(optionsHtml);
        }
        $dropdown.val(currentPlaylistIndex);
        
        // Update external player buttons
        updateExternalPlayerButtons();
    }
    
    /**
     * Update external player buttons
     */
    function updateExternalPlayerButtons() {
        var currentFile = playlist[currentPlaylistIndex];
        if (!currentFile) return;
        
        // For internal Video.js player: use stream_video (session auth)
        // For external players: fetch token and use /normal/ route (no auth)
        var filePath = currentFile.path || '';
        var directStreamUrl = currentFile.stream_url || '';
        var filename = currentFile.name || 'video.mp4';
        var imgBase = '/' + config.package_name + '/static/img/players/';
        
        // First, show loading state
        $('#external-player-buttons').html('<span class="text-muted">Loading...</span>');

        // Remote/direct stream case
        if (directStreamUrl || isHttpLikeUrl(filePath)) {
            var remoteUrl = toAbsoluteUrl(directStreamUrl || filePath);
            renderExternalPlayerButtons(remoteUrl, filename, imgBase);
            return;
        }
        
        // Fetch a streaming token for external players
        $.ajax({
            url: '/' + config.package_name + '/ajax/' + config.sub + '/generate_stream_token?path=' + encodeURIComponent(filePath),
            type: 'GET',
            dataType: 'json',
            success: function(data) {
                if (data.ret === 'success' && data.token) {
                    var tokenUrl = window.location.origin + '/' + config.package_name + '/normal/' + config.sub + '/stream_with_token?token=' + data.token;
                    renderExternalPlayerButtons(tokenUrl, filename, imgBase);
                } else {
                    // Fallback: use stream_video with path (may require auth)
                    console.warn('[VideoModal] Token generation failed, using fallback');
                    var fallbackUrl = window.location.origin + '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(filePath);
                    renderExternalPlayerButtons(fallbackUrl, filename, imgBase);
                }
            },
            error: function() {
                // Fallback: use stream_video with path
                console.warn('[VideoModal] Token generation error, using fallback');
                var fallbackUrl = window.location.origin + '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(filePath);
                renderExternalPlayerButtons(fallbackUrl, filename, imgBase);
            }
        });
    }
    
    /**
     * Render external player buttons with the given stream URL
     */
    function renderExternalPlayerButtons(streamUrl, filename, imgBase) {
        var encodedUrl = encodeURIComponent(streamUrl);
        var doubleEncodedUrl = encodeURIComponent(encodedUrl);
        
        var players = [
            { name: 'IINA', img: imgBase + 'iina.webp', url: 'iina://weblink?url=' + encodedUrl },
            { name: 'PotPlayer', img: imgBase + 'potplayer.webp', url: 'potplayer://' + streamUrl },
            { name: 'VLC', img: imgBase + 'vlc.webp', url: 'intent:' + streamUrl + '#Intent;package=org.videolan.vlc;type=video/*;end' },
            { name: 'nPlayer', img: imgBase + 'nplayer.webp', url: 'nplayer-' + streamUrl },
            { name: 'Infuse', img: imgBase + 'infuse.webp', url: 'infuse://x-callback-url/play?url=' + streamUrl },
            { name: 'OmniPlayer', img: imgBase + 'omniplayer.webp', url: 'omniplayer://weblink?url=' + streamUrl },
            { name: 'MX Player', img: imgBase + 'mxplayer.webp', url: 'intent:' + streamUrl + '#Intent;package=com.mxtech.videoplayer.ad;type=video/mp4;S.title=' + encodeURIComponent(filename) + ';end' },
            { name: 'MPV', img: imgBase + 'mpv.webp', url: 'mpv://' + doubleEncodedUrl },
        ];
        
        var html = '';
        for (var i = 0; i < players.length; i++) {
            var p = players[i];
            html += '<a href="' + p.url + '" class="ext-player-btn" title="' + p.name + '">';
            html += '<img src="' + p.img + '" alt="' + p.name + '">';
            html += '</a>';
        }
        
        $('#external-player-buttons').html(html);
    }
    
    /**
     * Close the modal
     */
    function close() {
        $('#videoModal').modal('hide');
    }
    
    /**
     * Get current playlist
     */
    function getPlaylist() {
        return playlist;
    }
    
    /**
     * Get current index
     */
    function getCurrentIndex() {
        return currentPlaylistIndex;
    }
    
    // Public API
    return {
        init: init,
        openWithPath: openWithPath,
        openWithUrl: openWithUrl,
        openWithPlaylist: openWithPlaylist,
        playVideoAtIndex: playVideoAtIndex,
        close: close,
        getPlaylist: getPlaylist,
        getCurrentIndex: getCurrentIndex
    };
})();

// Auto-initialize when DOM is ready (uses global package_name and sub variables)
$(document).ready(function() {
    // Use global variables if available (set by each page)
    var pkgName = (typeof package_name !== 'undefined') ? package_name : 'anime_downloader';
    var subName = (typeof sub !== 'undefined') ? sub : 'ohli24';
    
    VideoModal.init({ package_name: pkgName, sub: subName });
    
    // Auto-bind btn-watch click handler
    $('body').on('click', '.btn-watch', function(e) {
        e.preventDefault();
        var filePath = $(this).data('path');
        if (filePath) {
            VideoModal.openWithPath(filePath);
        }
    });
});
