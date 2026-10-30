import base64
import unittest
from computer_activity import project, image_bytes

class ActivityTests(unittest.TestCase):
    def message(self, uri):
        return {'id': 'msg_test', 'content': [{'type': 'tool', 'id': 'call_test', 'name': 'linux_computer_observe',
            'state': {'status': 'completed', 'input': {'secret': 'must-not-project'},
                      'content': [{'type': 'file', 'mime': 'image/png', 'uri': uri}]}, 'time': {'created': 1}}]}
    def test_only_recorded_image_no_paths_or_network(self):
        for uri in ('file:///etc/passwd', 'https://example.com/image.png', '/private/image.png'):
            message = self.message(uri)
            self.assertEqual(project([message])[0]['images'], [])
            with self.assertRaises(ValueError): image_bytes(message, 'call_test', 0)
    def test_projection_contains_no_input_or_image_bytes(self):
        message = self.message('data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode())
        steps = project([message])
        self.assertNotIn('secret', str(steps)); self.assertNotIn('base64', str(steps))
        self.assertEqual(image_bytes(message, 'call_test', 0)[0], 'image/png')
        with self.assertRaises(ValueError): image_bytes(message, 'other', 0)
        with self.assertRaises(ValueError): image_bytes(message, 'call_test', -1)
    def test_invalid_magic_and_noncomputer_tools(self):
        message = self.message('data:image/png;base64,' + base64.b64encode(b'<html>bad</html>').decode())
        with self.assertRaises(ValueError): image_bytes(message, 'call_test', 0)
        message['content'][0]['name'] = 'read'
        self.assertEqual(project([message]), [])
