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
    var isVideoZoomed = false;
    
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
            initPlayerWithUrl(currentStreamUrl);
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
    
    /**
     * Initialize player with URL based on current player selection
     */
    function initPlayerWithUrl(streamUrl) {
        currentStreamUrl = streamUrl;
        
        if (currentPlayer === 'videojs') {
            initVideoJS(streamUrl);
        } else if (currentPlayer === 'artplayer') {
            initArtplayer(streamUrl);
        } else if (currentPlayer === 'plyr') {
            initPlyr(streamUrl);
        }
    }
    
    /**
     * Initialize Video.js player
     */
    function initVideoJS(streamUrl) {
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
        }
        
        videoPlayer.src({ type: 'video/mp4', src: streamUrl });
    }
    
    /**
     * Initialize Artplayer
     */
    function initArtplayer(streamUrl) {
        // Hide other containers
        $('#videojs-container').hide();
        $('#plyr-container').hide();
        $('#artplayer-container').show().empty();
        
        if (artPlayer) {
            artPlayer.destroy();
            artPlayer = null;
        }
        
        artPlayer = new Artplayer({
            container: '#artplayer-container',
            url: streamUrl,
            autoplay: false,
            pip: true,
            screenshot: true,
            setting: true,
            playbackRate: true,
            aspectRatio: true,
            fullscreen: true,
            fullscreenWeb: true,
            theme: '#3b82f6'
        });
        
        artPlayer.on('video:ended', handleVideoEnded);
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
        
        if (!plyrPlayer) {
            plyrPlayer = new Plyr('#plyr-player', {
                controls: ['play-large', 'play', 'progress', 'current-time', 'mute', 'volume', 'settings', 'pip', 'fullscreen'],
                settings: ['quality', 'speed'],
                speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] }
            });
            
            plyrPlayer.on('ended', handleVideoEnded);
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
        var streamUrl = '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(item.path);
        
        initPlayerWithUrl(streamUrl);
        
        // Try to auto-play
        setTimeout(function() {
            if (currentPlayer === 'videojs' && videoPlayer) videoPlayer.play();
            else if (currentPlayer === 'artplayer' && artPlayer) artPlayer.play = true;
            else if (currentPlayer === 'plyr' && plyrPlayer) plyrPlayer.play();
        }, 100);
        
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
                
                var streamUrl = '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(filePath);
                initPlayerWithUrl(streamUrl);
                updatePlaylistUI();
                $('#videoModal').modal('show');
            },
            error: function() {
                playlist = [{ name: filePath.split('/').pop(), path: filePath }];
                currentPlaylistIndex = 0;
                var streamUrl = '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(filePath);
                initPlayerWithUrl(streamUrl);
                updatePlaylistUI();
                $('#videoModal').modal('show');
            }
        });
    }
    
    /**
     * Open modal with a direct stream URL
     */
    function openWithUrl(streamUrl, title) {
        playlist = [{ name: title || 'Video', path: streamUrl }];
        currentPlaylistIndex = 0;
        initPlayerWithUrl(streamUrl);
        updatePlaylistUI();
        $('#videoModal').modal('show');
    }
    
    /**
     * Open modal with a playlist array
     */
    function openWithPlaylist(playlistData, startIndex) {
        playlist = playlistData || [];
        currentPlaylistIndex = startIndex || 0;
        if (playlist.length > 0) {
            var filePath = playlist[currentPlaylistIndex].path;
            var streamUrl = '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(filePath);
            initPlayerWithUrl(streamUrl);
            updatePlaylistUI();
            $('#videoModal').modal('show');
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
        if (!currentFile || !currentFile.path) return;
        
        // For internal Video.js player: use stream_video (session auth)
        // For external players: fetch token and use /normal/ route (no auth)
        var filePath = currentFile.path;
        var filename = currentFile.name || 'video.mp4';
        var imgBase = '/' + config.package_name + '/static/img/players/';
        
        // First, show loading state
        $('#external-player-buttons').html('<span class="text-muted">Loading...</span>');
        
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
