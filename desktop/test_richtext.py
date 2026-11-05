import unittest

from backend import artifacts
from richtext import MAX_TEXT, display_text, local_links, markup, parse, plain, safe_url, table_tsv, walk


class MarkdownTests(unittest.TestCase):
    def nodes(self, text, tag):
        return [n for n in walk(parse(text).root) if n.tag == tag]

    def test_headings_inline_styles_entities_and_soft_hard_breaks(self):
        doc = parse('# Title\n\n**bold**, *italic*, ~~removed~~ and `x < y`. &copy;\nsoft\n\nhard  \nbreak')
        tags = {n.tag for n in walk(doc.root)}
        self.assertTrue({'h1', 'strong', 'em', 'del', 'code', 'br'} <= tags)
        result = markup(doc.root)
        self.assertIn('<b>bold</b>', result)
        self.assertIn('<s>removed</s>', result)
        self.assertIn('© soft', result)
        self.assertIn('hard\nbreak', result)
        self.assertIn('&lt;', result)

    def test_ordered_nested_and_readonly_task_lists(self):
        doc = parse('3. Third\n4. Fourth\n\n- Parent\n    - Nested **item**\n- [x] Completed\n- [ ] Pending')
        nodes = list(walk(doc.root))
        ordered = next(n for n in nodes if n.tag == 'ol')
        self.assertEqual(ordered.attrs.get('start'), '3')
        self.assertGreaterEqual(sum(n.tag == 'ul' for n in nodes), 2)
        tasks = [n.attrs.get('data-task') for n in nodes if n.tag == 'li' and 'data-task' in n.attrs]
        self.assertEqual(tasks, ['checked', 'unchecked'])
        self.assertNotIn('[x]', plain(doc.root))

    def test_fenced_makefile_preserves_tabs_and_literal_html(self):
        source = '```makefile\nall:\n\t@echo "<script>not executed</script>"\n```'
        code = self.nodes(source, 'code')[0]
        self.assertEqual(plain(code), 'all:\n\t@echo "<script>not executed</script>"\n')
        self.assertIn('language-makefile', code.attrs['class'])
        self.assertNotIn('script', {n.tag for n in walk(code)})

    def test_longer_fence_and_unfinished_streaming_fence(self):
        doc = parse('````text\n```\ninside\n```\n````')
        code = next(n for n in walk(doc.root) if n.tag == 'code')
        self.assertEqual(plain(code), '```\ninside\n```\n')
        unfinished = self.nodes('~~~python\nprint("streaming")', 'code')[0]
        self.assertEqual(plain(unfinished), 'print("streaming")')

    def test_fence_titles_and_unsafe_attributes_never_leak_stash_tokens(self):
        for info in ('python title="app.py"', '<img onerror="x">', '{.python #custom-id}'):
            with self.subTest(info=info):
                doc = parse('```' + info + '\n<script>literal</script>\n```')
                code = next(n for n in walk(doc.root) if n.tag == 'code')
                self.assertEqual(plain(code), '<script>literal</script>\n')
                self.assertNotIn('POCKETCODE', plain(doc.root))

    def test_indented_code_and_quotes_and_separator(self):
        doc = parse('> quoted **text**\n>\n> more\n\n---\n\n    indented <literal>')
        tags = {n.tag for n in walk(doc.root)}
        self.assertTrue({'blockquote', 'hr', 'pre', 'code'} <= tags)
        self.assertIn('indented <literal>', plain(doc.root))

    def test_tables_alignment_escaped_pipe_and_tsv(self):
        source = '| Name | Result | Count |\n| :--- | :---: | ---: |\n| a\\|b | **good** | 3 |\n| second | `ready` | 7 |'
        table = self.nodes(source, 'table')[0]
        cells = [n for n in walk(table) if n.tag in ('td', 'th')]
        self.assertIn('text-align: right', cells[2].attrs['style'])
        self.assertEqual(table_tsv(table), 'Name\tResult\tCount\na|b\tgood\t3\nsecond\tready\t7')

    def test_reference_links_autolinks_and_escaped_markup(self):
        doc = parse('[Docs][guide]\n\n[guide]: https://Example.COM/a?x=1&y=2 "title"\n\n<https://example.com/other>\n\n\\*not emphasis\\*')
        links = [n for n in walk(doc.root) if n.tag == 'a']
        self.assertEqual(len(links), 2)
        self.assertEqual(safe_url(links[0].attrs['href']), 'https://example.com/a?x=1&y=2')
        self.assertIn('&amp;y=2', markup(doc.root))
        self.assertIn('*not emphasis*', plain(doc.root))

    def test_raw_html_is_literal_not_native_markup(self):
        source = '<script>alert("x")</script>\n\n<iframe src="https://example.com"></iframe>\n\n<span foreground="red">untrusted</span>'
        doc = parse(source); tags = {n.tag for n in walk(doc.root)}
        self.assertFalse({'script', 'iframe', 'span'} & tags)
        self.assertIn('<script>', plain(doc.root))
        self.assertIn('&lt;script&gt;', markup(doc.root))
        self.assertNotIn('<span foreground=', markup(doc.root))

    def test_images_are_inert_and_never_create_a_native_loader(self):
        doc = parse('![tracking](https://example.com/tracker.png)')
        self.assertIn('carregamento automático desativado', markup(doc.root))
        self.assertNotIn('href=', markup(doc.root))

    def test_links_reject_scripts_credentials_controls_headers_and_bidi(self):
        values = ['javascript:alert(1)', 'data:text/html,<script>x</script>', 'file:///etc/passwd', 'ftp://example.com', '//example.com/path',
                  'https://user:password@example.com', 'https://example.com/%250aheader', 'https://example.com/\x00',
                  'https://example.com/\\evil', 'https://example.com/\u202espoof', 'https://example.com/%E2%80%AEspoof',
                  'https://example.com/\u061cspoof', 'https://example.com/%EF%BB%BFhidden', 'https://example.com/%C2%85hidden',
                  'https://example.com:99999', 'https://[bad', 'mailto:test@example.com?body=secret', 'mailto:a@example.com#fragment', 'mailto:user%3Fbody%3Dsecret@example.com']
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(safe_url(value))

    def test_safe_destinations_are_normalized_and_visible(self):
        self.assertEqual(safe_url('https://ExAmPlE.com/path%20one?x=1&y=2#part'), 'https://example.com/path%20one?x=1&y=2#part')
        self.assertEqual(safe_url('https://münich.example/ação'), 'https://xn--mnich-kva.example/a%C3%A7%C3%A3o')
        self.assertIsNone(safe_url('https://straße.example/'))  # Do not silently map ß to another ASCII domain.
        self.assertEqual(safe_url('https://xn--strae-oqa.example/'), 'https://xn--strae-oqa.example/')
        self.assertEqual(safe_url('http://[::1]:8000/'), 'http://[::1]:8000/')
        self.assertEqual(safe_url('mailto:dev+test@example.com'), 'mailto:dev+test@example.com')

    def test_code_examples_do_not_become_generated_file_actions(self):
        doc = parse('```markdown\n[Example](example.txt)\n```\n\n[Real file](out/result.txt)\n\n[Bad](http://[invalid)')
        references = local_links(doc.root)
        self.assertEqual(references, [('Real file', 'out/result.txt')])
        files = artifacts({'text': 'unused'}, '/project', links=references)
        self.assertEqual([f['path'] for f in files], ['/project/out/result.txt'])

    def test_limits_fall_back_without_discarding_original(self):
        doc = parse('a'*(MAX_TEXT+10))
        self.assertTrue(doc.notices); self.assertEqual(len(doc.original), MAX_TEXT+10)
        deep = parse('>'*100 + ' nested')
        self.assertTrue(deep.notices)
        many_fences = parse('```text\nx\n```\n\n'*140)
        self.assertTrue(many_fences.notices)

    def test_display_controls_and_crlf_do_not_break_pango(self):
        self.assertEqual(display_text('a\r\nb\t\x00'), 'a\nb\t\ufffd')
        self.assertEqual(display_text('\ud800'), '\ufffd')
        self.assertFalse(artifacts({'text': '[bad](out/\ud800.txt)'}, '/project'))


if __name__ == '__main__':
    unittest.main()
