"""Trusted browser checkpoints in the existing conversation directory."""
import json
import re
import secrets
import stat

from .business_contract import read_safe
from .session_context import SessionContextError


class WebSession:
    def __init__(self, conversation, chat_id, task):
        self.path = conversation._session_dir(chat_id) / 'web_session.json'
        self.state = {}
        if self.path.exists() or self.path.is_symlink():
            try:
                self.state = json.loads(read_safe(self.path.parent,self.path,65536))
            except (ValueError,OSError):
                raise SessionContextError('Invalid dedicated browser checkpoint') from None
            if (not isinstance(self.state,dict) or set(self.state) != {'profile','tab','url','download'}
                or self.state.get('profile') != 'saccade-dext'
                or not isinstance(self.state['tab'],str) or not self.state['tab'].isdigit()
                or not isinstance(self.state['url'],str) or len(self.state['url'])>8192
                or self.state['download'] is not None and not isinstance(self.state['download'],dict)):
                raise SessionContextError('Invalid dedicated browser checkpoint')
        self.requires_dext = bool(self.state) or bool(re.search(r'(?i)\bdext\b',task))

    def profile(self):
        return 'saccade-dext' if self.requires_dext else None

    def save(self, tab, url, download=None):
        from .automatic_platform import detect_platform
        if detect_platform(url) != 'dext':
            download = None
        self.state = {'profile':'saccade-dext','tab':str(tab),'url':url,'download':download}
        self.path.parent.mkdir(parents=True,exist_ok=True)
        metadata=self.path.parent.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or getattr(metadata,'st_file_attributes',0)&0x400:
            raise SessionContextError('Unsafe browser checkpoint directory')
        payload=json.dumps(self.state,ensure_ascii=False)
        if len(payload.encode('utf8'))>65536:
            raise SessionContextError('Browser checkpoint exceeds its size limit')
        temporary=self.path.with_name('web_session.'+secrets.token_hex(8)+'.tmp')
        try:
            with temporary.open('x',encoding='utf8') as stream: stream.write(payload)
            temporary.replace(self.path)
        finally:
            if temporary.exists(): temporary.unlink()

    def target(self):
        return self.state.get('tab'),self.state.get('url')

    def download(self):
        return self.state.get('download')

    def observed_target(self, tab, url):
        """Authentication/navigation changes are observations, not replay consent."""
        if self.target() != (str(tab),url):
            self.save(tab,url,None)
