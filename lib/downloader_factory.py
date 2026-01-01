import logging
import os
import traceback
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

class BaseDownloader:
    """Base interface for all downloaders"""
    def download(self) -> bool:
        raise NotImplementedError()
        
    def cancel(self):
        raise NotImplementedError()

class FfmpegDownloader(BaseDownloader):
    """Wrapper for SupportFfmpeg to provide a standard interface"""
    def __init__(self, support_ffmpeg_obj):
        self.obj = support_ffmpeg_obj
        
    def download(self) -> bool:
        # SupportFfmpeg.start() returns data but runs in its own thread.
        # We start and then join to make it a blocking download() call.
        self.obj.start()
        if self.obj.thread:
            self.obj.thread.join()
        
        # Check status from SupportFfmpeg.Status
        from support.expand.ffmpeg import SupportFfmpeg
        return self.obj.status == SupportFfmpeg.Status.COMPLETED

    def cancel(self):
        self.obj.stop()

class DownloaderFactory:
    @staticmethod
    def get_downloader(
        method: str,
        video_url: str,
        output_file: str,
        headers: Optional[Dict[str, str]] = None,
        callback: Optional[Callable] = None,
        proxy: Optional[str] = None,
        threads: int = 16,
        **kwargs
    ) -> Optional[BaseDownloader]:
        """
        Returns a downloader instance based on the specified method.
        """
        try:
            logger.info(f"Creating downloader for method: {method}")
            
            if method == "cdndania":
                from .cdndania_downloader import CdndaniaDownloader
                # cdndania needs iframe_src, usually passed in headers['Referer'] 
                # or as a separate kwarg from the entity.
                iframe_src = kwargs.get('iframe_src')
                if not iframe_src and headers:
                    iframe_src = headers.get('Referer')
                
                if not iframe_src:
                    iframe_src = video_url
                    
                return CdndaniaDownloader(
                    iframe_src=iframe_src,
                    output_path=output_file,
                    referer_url=kwargs.get('referer_url', "https://ani.ohli24.com/"),
                    callback=callback,
                    proxy=proxy,
                    threads=threads,
                    on_download_finished=kwargs.get('on_download_finished')
                )
                
            elif method == "ytdlp" or method == "aria2c":
                from .ytdlp_downloader import YtdlpDownloader
                return YtdlpDownloader(
                    url=video_url,
                    output_path=output_file,
                    headers=headers,
                    callback=callback,
                    proxy=proxy,
                    cookies_file=kwargs.get('cookies_file'),
                    use_aria2c=(method == "aria2c"),
                    threads=threads
                )
                
            elif method == "hls":
                from .hls_downloader import HlsDownloader
                return HlsDownloader(
                    m3u8_url=video_url,
                    output_path=output_file,
                    headers=headers,
                    callback=callback,
                    proxy=proxy
                )
                
            elif method == "ffmpeg" or method == "normal":
                from support.expand.ffmpeg import SupportFfmpeg
                # SupportFfmpeg needs some global init but let's assume it's done index.py/plugin.py
                dirname = os.path.dirname(output_file)
                filename = os.path.basename(output_file)
                
                # We need to pass callback_function that adapts standard callback (percent, current, total...)
                # to what SupportFfmpeg expects if necessary.
                # However, SupportFfmpeg handling is usually done via listener in ffmpeg_queue_v1.py.
                # So we might return the SupportFfmpeg object itself wrapped.
                
                ffmpeg_obj = SupportFfmpeg(
                    url=video_url,
                    filename=filename,
                    save_path=dirname,
                    headers=headers,
                    proxy=proxy,
                    callback_id=kwargs.get('callback_id'),
                    callback_function=kwargs.get('callback_function')
                )
                return FfmpegDownloader(ffmpeg_obj)
                
            else:
                logger.error(f"Unknown download method: {method}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create downloader: {e}")
            logger.error(traceback.format_exc())
            return None
