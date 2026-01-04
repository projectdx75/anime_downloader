/**
 * Video Modal Component JavaScript
 * Reusable video player modal for Anime Downloader
 * 
 * Usage:
 *   VideoModal.init({ package_name: 'anime_downloader', sub: 'ohli24' });
 *   VideoModal.openWithPath('/path/to/video.mp4');
 */

var VideoModal = (function() {
    'use strict';
    
    var config = {
        package_name: 'anime_downloader',
        sub: 'ohli24'
    };
    
    var videoPlayer = null;
    var playlist = [];
    var currentPlaylistIndex = 0;
    var currentPlayingPath = '';
    var isVideoZoomed = false;
    
    /**
     * Initialize the video modal
     * @param {Object} options - Configuration options
     * @param {string} options.package_name - Package name (default: 'anime_downloader')
     * @param {string} options.sub - Sub-module name (e.g., 'ohli24', 'linkkf')
     */
    function init(options) {
        config = Object.assign(config, options || {});
        bindEvents();
        console.log('[VideoModal] Initialized with config:', config);
    }
    
    /**
     * Bind all event handlers
     */
    function bindEvents() {
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
                $('#video-player').css({
                    'object-fit': 'cover',
                    'max-height': '100vh'
                });
                $(this).addClass('active').find('i').removeClass('fa-expand').addClass('fa-compress');
            } else {
                $('#video-player').css({
                    'object-fit': 'contain',
                    'max-height': '80vh'
                });
                $(this).removeClass('active').find('i').removeClass('fa-compress').addClass('fa-expand');
            }
        });
        
        // Modal events
        $('#videoModal').off('show.bs.modal').on('show.bs.modal', function() {
            $('body').addClass('modal-video-open');
        });
        
        $('#videoModal').off('hide.bs.modal').on('hide.bs.modal', function() {
            if (videoPlayer) {
                videoPlayer.pause();
            }
        });
        
        $('#videoModal').off('hidden.bs.modal').on('hidden.bs.modal', function() {
            $('body').removeClass('modal-video-open');
            if (isVideoZoomed) {
                isVideoZoomed = false;
                $('#video-player').css({
                    'object-fit': 'contain',
                    'max-height': '80vh'
                });
                $('#btn-video-zoom').removeClass('active').find('i').removeClass('fa-compress').addClass('fa-expand');
            }
        });
    }
    
    /**
     * Open modal with a file path (fetches playlist from server)
     * @param {string} filePath - Path to the video file
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
                initPlayer(streamUrl);
                updatePlaylistUI();
                $('#videoModal').modal('show');
            },
            error: function() {
                // Fallback: single file
                playlist = [{ name: filePath.split('/').pop(), path: filePath }];
                currentPlaylistIndex = 0;
                var streamUrl = '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(filePath);
                initPlayer(streamUrl);
                updatePlaylistUI();
                $('#videoModal').modal('show');
            }
        });
    }
    
    /**
     * Open modal with a direct stream URL
     * @param {string} streamUrl - Direct URL to stream
     * @param {string} title - Optional title
     */
    function openWithUrl(streamUrl, title) {
        playlist = [{ name: title || 'Video', path: streamUrl }];
        currentPlaylistIndex = 0;
        initPlayer(streamUrl);
        updatePlaylistUI();
        $('#videoModal').modal('show');
    }
    
    /**
     * Open modal with a playlist array
     * @param {Array} playlistData - Array of {name, path} objects
     * @param {number} startIndex - Index to start playing from
     */
    function openWithPlaylist(playlistData, startIndex) {
        playlist = playlistData || [];
        currentPlaylistIndex = startIndex || 0;
        if (playlist.length > 0) {
            var filePath = playlist[currentPlaylistIndex].path;
            var streamUrl = '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(filePath);
            initPlayer(streamUrl);
            updatePlaylistUI();
            $('#videoModal').modal('show');
        }
    }
    
    /**
     * Initialize or update Video.js player
     * @param {string} streamUrl - URL to play
     */
    function initPlayer(streamUrl) {
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
            
            // Auto-next on video end
            videoPlayer.on('ended', function() {
                var autoNextEnabled = $('#auto-next-checkbox').is(':checked');
                if (autoNextEnabled && currentPlaylistIndex < playlist.length - 1) {
                    currentPlaylistIndex++;
                    playVideoAtIndex(currentPlaylistIndex);
                }
            });
        }
        
        videoPlayer.src({ type: 'video/mp4', src: streamUrl });
    }
    
    /**
     * Play video at specific playlist index
     * @param {number} index - Playlist index
     */
    function playVideoAtIndex(index) {
        if (index < 0 || index >= playlist.length) return;
        currentPlaylistIndex = index;
        var item = playlist[index];
        var streamUrl = '/' + config.package_name + '/ajax/' + config.sub + '/stream_video?path=' + encodeURIComponent(item.path);
        
        if (videoPlayer) {
            videoPlayer.src({ type: 'video/mp4', src: streamUrl });
            videoPlayer.play();
        }
        
        updatePlaylistUI();
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
            { name: 'VLC', img: imgBase + 'vlc.webp', url: 'vlc:' + streamUrl },
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
