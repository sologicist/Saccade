"""Conversation-bound browser checkpoints; no Chrome or private files."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from AutoCua.saccade.web_session import WebSession


class WebSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.conversation=SimpleNamespace(_session_dir=lambda sid:self.root/sid)

    def test_explicit_dext_request_uses_dedicated_profile_without_platform_context(self):
        session=WebSession(self.conversation,'chat_one','Open Dext and analyze the invoice')
        self.assertEqual(session.profile(),'saccade-dext')
        self.assertIsNone(WebSession(self.conversation,'chat_two','Search a public website').profile())

    def test_same_chat_restores_target_and_other_chat_does_not_inherit_it(self):
        session=WebSession(self.conversation,'chat_one','Open Dext')
        session.save('7','https://app.dext.com/synthetic-invoice',{'path':'synthetic','sha256':'a'*64})
        restored=WebSession(self.conversation,'chat_one','Analyze the file already downloaded')
        self.assertEqual(restored.profile(),'saccade-dext')
        self.assertEqual(restored.target(),('7','https://app.dext.com/synthetic-invoice'))
        self.assertEqual(restored.download()['sha256'],'a'*64)
        self.assertIsNone(WebSession(self.conversation,'chat_two','Analyze a file').download())

    def test_leaving_dext_discards_document_association(self):
        session=WebSession(self.conversation,'chat_one','Open Dext')
        session.save('7','https://example.com/',{'path':'synthetic'})
        self.assertIsNone(session.download())

    def test_authentication_redirect_keeps_profile_but_invalidates_old_pdf(self):
        session=WebSession(self.conversation,'chat_one','Open Dext')
        session.save('7','https://app.dext.com/sign/in',{'path':'old'})
        session.observed_target('7','https://app.dext.com/delta/clients')
        self.assertEqual(session.profile(),'saccade-dext')
        self.assertEqual(session.target(),('7','https://app.dext.com/delta/clients'))
        self.assertIsNone(session.download())

    def test_malformed_checkpoint_is_not_a_generic_profile_fallback(self):
        folder=self.root/'chat_one';folder.mkdir()
        (folder/'web_session.json').write_text(json.dumps({'profile':'personal'}))
        with self.assertRaises(ValueError): WebSession(self.conversation,'chat_one','Continue')
