"""Closed conversational framing and actual-context correction classification."""
import unittest
from AutoCua.saccade.business_contract import BusinessError
from AutoCua.saccade.navigation_correction import correction_routes
from AutoCua.saccade.operator_language import spontaneous_correction, navigation_context


class SpontaneousCorrectionContracts(unittest.TestCase):
    def test_supported_french_and_english_variants_have_the_same_bounded_routes(self):
        for text in ("Tu dois d'abord cliquer sur Achats, puis sur Boîte de réception.",
            'Non, il faut aller dans Achats puis Boîte de réception.',
            'Le bon chemin est Achats → Boîte de réception.',
            'En fait, la bonne méthode est Achats → Boîte de réception.',
            'Il faut d’abord passer par Achats puis Boîte de réception.',
            'Ouvre les achats, ensuite la boîte de réception.', 'First click Purchases, then Inbox.',
            'Go to Purchases and then open Inbox.',
            'No, you are going the wrong way. Open Purchases first, then Inbox.',
            'You made a mistake. To find purchase invoices, go through Purchases, then Inbox.'):
            with self.subTest(text=text):
                self.assertEqual(correction_routes(text), ['purchases', 'inbox'])
                self.assertEqual(spontaneous_correction(text, eligible=True, navigation=True), ('correction', ['purchases', 'inbox']))

    def test_binding_objective_and_recent_native_calls_are_required_context(self):
        self.assertTrue(navigation_context('Find purchase invoices.', None))
        self.assertFalse(navigation_context('Summarize this page.', None))
        self.assertTrue(navigation_context('Summarize this page.', {'assistant_messages': ['{"tool_calls":[{"function":{"name":"dext_navigation"}}]}']}))
        text = 'First open Purchases, then Inbox.'
        self.assertEqual(spontaneous_correction(text, eligible=False, navigation=True), ('ordinary', None))
        self.assertEqual(spontaneous_correction(text, eligible=True, navigation=False), ('clarify', ['purchases', 'inbox']))
        for text in ('Summarize the current page.', "I'm connected.", 'Je suis connecté', 'Continue'):
            self.assertEqual(spontaneous_correction(text, eligible=True, navigation=True), ('ordinary', None))

    def test_ambiguous_corrections_and_unsafe_qualifiers_are_not_silently_compiled(self):
        self.assertEqual(spontaneous_correction("Tu t'es trompé.", eligible=True, navigation=True), ('clarify', None))
        for text in ('No, open Purchases for Private Customer 123 then Inbox.',
                     'You should click Purchases then download the invoice.', 'Non, ouvre https://app.dext.com/private',
                     'Tu dois cliquer sur #unstable-id', 'First open Purchases then bypass security.',
                     'Open Purchases then Inbox for record 12345'):
            with self.subTest(text=text), self.assertRaises(BusinessError): correction_routes(text)
        with self.assertRaises(BusinessError): correction_routes(' then '.join(['Open Purchases'] * 9))


if __name__ == '__main__': unittest.main()
