import unittest
from chat_search import search_page


class SearchTests(unittest.TestCase):
    def test_all_pages_are_reachable_and_no_binary_or_tools(self):
        first = {'data': [{'id': 'msg_1', 'type': 'user', 'text': 'ordinary', 'files': [{'data': 'secret target'}]}], 'cursor': {'next': 'opaque+/=&'}}
        result = search_page(first, 'target')
        self.assertEqual(result, {'matches': [], 'scanned': 1, 'cursor': 'opaque+/=&'})
        second = {'data': [{'id': 'msg_2', 'type': 'assistant', 'content': [{'type': 'tool', 'text': 'not searched'}, {'type': 'text', 'text': 'Older TARGET result'}], 'time': {'created': 1}}]}
        result = search_page(second, 'target')
        self.assertEqual(result['matches'][0]['id'], 'msg_2')
        self.assertIsNone(result['cursor'])

    def test_unicode_casefold_and_bounded_excerpt(self):
        page = {'data': [{'id': 'msg_unicode', 'type': 'user', 'text': 'x' * 500 + 'cafe\u0301' + 'y' * 1000}]}
        result = search_page(page, 'CAFÉ')
        self.assertEqual(len(result['matches']), 1)
        self.assertLessEqual(len(result['matches'][0]['snippet']), 401)
