"""Bounded Markdown -> inert document -> native GTK widgets. No webview.

HTML is disabled in Python-Markdown. Pango markup is generated only from our
allowlist, with escaped text/attributes. Links are inert until the host reviews
their normalized HTTP(S)/mailto destination. Images never fetch their source.
"""
from dataclasses import dataclass, field
import html
from html.parser import HTMLParser
from ipaddress import IPv6Address
import re
import secrets
import urllib.parse
import unicodedata
import xml.etree.ElementTree as ET

import markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

MAX_TEXT = 200000
MAX_NODES = 8192
MAX_DEPTH = 24
MAX_WIDGETS = 1600


def display_text(text):
    text = str(text).replace('\r\n', '\n').replace('\r', '\n')
    return ''.join(c if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127 and not 0xd800 <= ord(c) <= 0xdfff) else '\ufffd' for c in text)


def safe_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    def unsafe(text, raw=False):
        return any(c == '\\' or unicodedata.category(c) in ('Cc', 'Cf', 'Cs') or (raw and c == ' ') for c in text)
    if unsafe(value, raw=True):
        return None
    decoded = value
    for _ in range(3):
        decoded = urllib.parse.unquote(decoded)
        if unsafe(decoded):
            return None
    try:
        parts = urllib.parse.urlsplit(value)
        scheme = parts.scheme.lower()
        if scheme == 'mailto':
            if parts.netloc or parts.query or parts.fragment or parts.path.count('@') != 1 or '%' in parts.path:
                return None
            user, domain = parts.path.rsplit('@', 1)
            if not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+', user):
                return None
            host = domain.encode('idna').decode('ascii').lower()
            if not domain.isascii() and host.encode('ascii').decode('idna').lower() != domain.lower():
                return None
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
                return None
            return 'mailto:' + user + '@' + host
        if scheme not in ('http', 'https') or not parts.hostname or parts.username is not None or parts.password is not None:
            return None
        hostname = parts.hostname
        if ':' in hostname:
            host = '[' + str(IPv6Address(hostname)) + ']'
        else:
            host = hostname.encode('idna').decode('ascii').lower()
            if not hostname.isascii() and host.encode('ascii').decode('idna').lower() != hostname.lower():
                return None
            if not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.rstrip('.').split('.')):
                return None
        if parts.port is not None:
            if not 1 <= parts.port <= 65535:
                return None
            host += ':' + str(parts.port)
        result = urllib.parse.urlunsplit((scheme, host, urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~"), urllib.parse.quote(parts.query, safe="%:@!$&'()*+,;=/?-._~"), urllib.parse.quote(parts.fragment, safe="%:@!$&'()*+,;=/?-._~")))
        return result if len(result.encode()) <= 4096 else None
    except (ValueError, UnicodeError):
        return None


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)


@dataclass
class Document:
    root: Node
    original: str
    notices: list = field(default_factory=list)


class RenderLimit(Exception):
    pass


class Strike(InlineProcessor):
    def handleMatch(self, match, data):
        node = ET.Element('del'); node.text = match.group(1)
        return node, match.start(), match.end()


class Tasks(Treeprocessor):
    def run(self, root):
        for node in root.iter('li'):
            target = node if node.text else (node[0] if len(node) and node[0].tag == 'p' else None)
            if target is None:
                continue
            match = re.match(r'^\[([ xX])\]\s+', target.text or '')
            if match:
                node.set('data-task', 'checked' if match.group(1).lower() == 'x' else 'unchecked')
                target.text = target.text[match.end():]


class NativeExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.deregister('html_block')
        md.inlinePatterns.deregister('html')
        md.ESCAPED_CHARS = list(md.ESCAPED_CHARS) + ['~']
        md.inlinePatterns.register(Strike(r'(?<!\\)~~(?=\S)(.+?)(?<=\S)~~', md), 'native_strike', 175)
        md.treeprocessors.register(Tasks(md), 'native_tasks', 15)


class InertParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root'); self.stack = [self.root]; self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > MAX_NODES or len(self.stack) > MAX_DEPTH:
            raise RenderLimit()
        allowed = {'href', 'title', 'alt', 'src', 'class', 'start', 'style', 'data-task'}
        node = Node(tag, {key: value for key, value in attrs if key in allowed and isinstance(value, str)})
        self.stack[-1].children.append(node)
        if tag not in ('br', 'hr', 'img'):
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag and tag not in ('br', 'hr', 'img'):
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]; break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def plain(node):
    if isinstance(node, str):
        return node
    if node.tag == 'br':
        return '\n'
    if node.tag == 'img':
        return '[Imagem: ' + node.attrs.get('alt', '') + ']'
    return ''.join(plain(child) for child in node.children)


def walk(node):
    if isinstance(node, Node):
        yield node
        for child in node.children:
            yield from walk(child)


def stash_fences(text):
    """Preserve literal tabs/code before Markdown whitespace normalization.

Also close a still-streaming root fence for its preview. Restored code becomes
inert node text, never HTML or an instruction to run a language interpreter.
"""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').splitlines(keepends=True)
    result = []; values = {}; index = 0; nonce = secrets.token_hex(12)
    while index < len(lines):
        match = re.match(r'^ {0,3}(`{3,}|~{3,})([^\n]*)\n?$', lines[index])
        if not match or (match.group(1)[0] == '`' and '`' in match.group(2)):
            result.append(lines[index]); index += 1; continue
        fence, info = match.groups(); end = index + 1
        if len(values) >= 128:
            raise RenderLimit()
        closing = re.compile(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*$')
        while end < len(lines) and not closing.match(lines[end]):
            end += 1
        token = 'POCKETCODE' + nonce + str(len(values))
        values[token] = ''.join(lines[index + 1:end])
        first = info.strip().split()[0] if info.strip() else ''
        language = first if re.fullmatch(r'[\w+#.-]{1,40}', first) else ''
        # Ignore arbitrary fence attributes; never pass them to an HTML/CSS
        # renderer or leak a stash token when another dialect uses titles.
        result.extend(['\n', fence + language + '\n', token + '\n', fence + '\n'])
        index = end + 1
    return ''.join(result), values


def parse(text):
    source = str(text); notices = []
    if len(source) > MAX_TEXT:
        notices.append('Mensagem longa: prévia limitada. Copie o texto completo para conferir o restante.')
    preview = source[:MAX_TEXT]
    try:
        prepared, codes = stash_fences(preview)
        if sum(prepared.count(token) for token in ('[', ']', '*', '_', '`', '<', '>')) > 30000:
            raise RenderLimit()
        converted = markdown.markdown(prepared, extensions=['tables', 'fenced_code', 'sane_lists', NativeExtension()], output_format='xhtml')
        if len(converted) > 2*1024*1024:
            raise RenderLimit()
        parser = InertParser(); parser.feed(converted); parser.close()
        restored = set()
        for node in walk(parser.root):
            if node.tag == 'code' and plain(node).strip() in codes:
                key = plain(node).strip(); node.children = [codes[key]]; restored.add(key)
        if len(restored) != len(codes):
            raise RenderLimit()
        return Document(parser.root, source, notices)
    except (RenderLimit, RecursionError, ValueError):
        notices.append('Estrutura Markdown extensa ou inválida: exibindo prévia de texto, sem executar conteúdo.')
        return Document(Node('root', children=[Node('p', children=[preview])]), source, notices)


def local_links(node):
    """Markdown references outside code; resolution remains the gateway's job."""
    result = []
    def visit(item):
        if not isinstance(item, Node) or item.tag in ('pre', 'code'):
            return
        if item.tag in ('a', 'img'):
            target = item.attrs.get('href' if item.tag == 'a' else 'src', '')
            try:
                parts = urllib.parse.urlsplit(target)
            except ValueError:
                return
            if parts.scheme in ('', 'file') and not parts.netloc and target:
                result.append((plain(item)[:200] or 'Arquivo', target))
        for child in item.children:
            visit(child)
    visit(node)
    return result


def markup(nodes, in_code=False):
    if isinstance(nodes, str):
        text = display_text(nodes)
        return html.escape(text if in_code else re.sub(r'[\t\r\n ]+', ' ', text))
    if isinstance(nodes, list):
        parts = []; after_break = False
        for child in nodes:
            if after_break and isinstance(child, str) and not in_code:
                child = child.lstrip(' \t\r\n')
                if not child:
                    continue
            parts.append(markup(child, in_code))
            after_break = isinstance(child, Node) and child.tag == 'br'
        return ''.join(parts)
    node = nodes; body = markup(node.children, in_code or node.tag == 'code')
    if node.tag == 'br':
        return '\n'
    if node.tag == 'img':
        return html.escape('[Imagem: ' + display_text(node.attrs.get('alt') or 'sem descrição') + ' — carregamento automático desativado]')
    tags = {'strong': 'b', 'em': 'i', 'del': 's', 'code': 'tt'}
    if node.tag in tags:
        return '<' + tags[node.tag] + '>' + body + '</' + tags[node.tag] + '>'
    if node.tag == 'a':
        target = safe_url(node.attrs.get('href'))
        return ('<a href="' + html.escape(target, quote=True) + '">' + body + '</a>') if target else body + ' [link não aberto]'
    return body


def table_rows(node):
    return [row for row in walk(node) if row.tag == 'tr']


def table_tsv(node):
    return '\n'.join('\t'.join(re.sub(r'[\t\r\n]+', ' ', plain(cell)) for cell in row.children if isinstance(cell, Node) and cell.tag in ('td', 'th')) for row in table_rows(node))


def render_native(text, on_link, on_copy):
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Pango
    document = parse(text)
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14); root.set_hexpand(True)
    root.markdown_links = local_links(document.root)
    root.markdown_document = document
    budget = {'count': 0}; notices = list(document.notices)
    block_tags = {'p', 'pre', 'ul', 'ol', 'li', 'table', 'blockquote', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    def charge():
        budget['count'] += 1
        if budget['count'] > MAX_WIDGETS:
            raise RenderLimit()

    def activate(_, target):
        normalized = safe_url(target)
        if normalized:
            on_link(normalized)
        return True  # Never let GTK launch a URI without host review.

    def paragraph(items, cls='message-text', header=False):
        charge()
        node = Node('p', children=items) if isinstance(items, list) else items
        if len(plain(node)) > 20000:
            notices.append('Parágrafo extenso: prévia limitada; texto completo disponível para copiar.')
            node = Node('p', children=[plain(node)[:20000]])
        widget = Gtk.Label(xalign=0, selectable=True, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        widget.set_hexpand(True); widget.set_max_width_chars(80); widget.add_css_class(cls)
        value = markup(node)
        widget.set_markup('<b>' + value + '</b>' if header else value)
        widget.connect('activate-link', activate)
        targets = [safe_url(n.attrs.get('href')) for n in walk(node) if n.tag == 'a']
        if any(targets):
            widget.set_tooltip_text('Links externos exigem confirmação:\n' + '\n'.join(t for t in targets if t))
        return widget

    def copy_button(title, value):
        charge()
        widget = Gtk.Button(label=title); widget.add_css_class('flat')
        widget.connect('clicked', lambda *_: on_copy(display_text(value)))
        return widget

    def blocks(nodes, target, depth=0):
        inline = []
        def flush():
            if inline and ''.join(plain(n) for n in inline).strip():
                target.append(paragraph(list(inline)))
            inline.clear()
        for item in nodes:
            if not isinstance(item, Node) or item.tag not in block_tags:
                inline.append(item); continue
            flush(); block(item, target, depth)
        flush()

    def block(node, target, depth):
        if depth > 12:
            notices.append('Aninhamento profundo: trecho exibido como texto.')
            target.append(paragraph(Node('p', children=[plain(node)]))); return
        tag = node.tag
        if tag == 'p' or tag.startswith('h') and tag[1:].isdigit():
            target.append(paragraph(node, 'md-' + tag if tag != 'p' else 'message-text', header=tag != 'p'))
        elif tag == 'hr':
            charge(); target.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        elif tag == 'blockquote':
            charge(); quote = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9); quote.add_css_class('md-quote')
            blocks(node.children, quote, depth + 1); target.append(quote)
        elif tag in ('ul', 'ol'):
            try:
                number = max(1, min(int(node.attrs.get('start', '1')), 100000))
            except ValueError:
                number = 1
            for item in node.children:
                if not isinstance(item, Node) or item.tag != 'li':
                    continue
                charge(); row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
                task = item.attrs.get('data-task')
                if task:
                    marker = Gtk.CheckButton(active=task == 'checked', sensitive=False)
                    marker.set_tooltip_text('Tarefa concluída (somente leitura)' if task == 'checked' else 'Tarefa pendente (somente leitura)')
                else:
                    marker = Gtk.Label(label=str(number) + '.' if tag == 'ol' else '•', xalign=1, yalign=0)
                    marker.set_width_chars(2); marker.set_max_width_chars(4); marker.set_ellipsize(Pango.EllipsizeMode.END)
                    marker.set_tooltip_text(marker.get_text())
                charge(); marker.set_valign(Gtk.Align.START); row.append(marker)
                body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9); body.set_hexpand(True); row.append(body)
                blocks(item.children, body, depth + 1); target.append(row); number += 1
        elif tag == 'pre':
            charge(); code = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); code.add_css_class('code-block')
            child = next((c for c in node.children if isinstance(c, Node) and c.tag == 'code'), node)
            raw = plain(child); language = re.search(r'language-([\w+#.-]{1,40})', child.attrs.get('class', ''))
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL); name = Gtk.Label(label=language.group(1) if language else 'Código', xalign=0, hexpand=True); name.set_ellipsize(Pango.EllipsizeMode.END); name.set_max_width_chars(20); name.add_css_class('dim-label'); header.append(name)
            header.append(copy_button('Copiar trecho' if document.notices else 'Copiar código', raw)); code.append(header)
            view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
            view.set_accepts_tab(False); view.add_css_class('md-code-view')
            view.get_buffer().set_text(display_text(raw[:100000]))
            scroll = Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.set_min_content_width(0); scroll.set_propagate_natural_width(False)
            scroll.set_min_content_height(min(240, max(48, (raw.count('\n') + 1)*19 + 16)))
            scroll.set_max_content_height(300); scroll.set_propagate_natural_height(True); scroll.set_child(view); code.append(scroll)
            if len(raw) > 100000:
                notices.append('Bloco de código extenso: exibição limitada; botão copia todo o bloco analisado.')
            target.append(code)
        elif tag == 'table':
            charge(); group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            group.append(copy_button('Copiar tabela (TSV)', table_tsv(node)))
            grid = Gtk.Grid(column_spacing=0, row_spacing=0)
            rows = table_rows(node)
            for y, row in enumerate(rows[:81]):
                cells = [c for c in row.children if isinstance(c, Node) and c.tag in ('td', 'th')]
                if len(cells) > 12:
                    notices.append('Tabela com mais de 12 colunas: prévia limitada; copie a tabela para conferir as demais.')
                for x, cell in enumerate(cells[:12]):
                    widget = paragraph(cell, 'md-table-cell', header=cell.tag == 'th')
                    widget.set_width_chars(9); widget.set_max_width_chars(26)
                    widget.add_css_class('md-table-head' if cell.tag == 'th' else ('md-table-alt' if y % 2 == 0 else 'md-table-body'))
                    align = re.search(r'text-align:\s*(left|center|right)', cell.attrs.get('style', ''))
                    widget.set_xalign({'left': 0, 'center': .5, 'right': 1}[align.group(1)] if align else 0)
                    grid.attach(widget, x, y, 1, 1)
            if len(rows) > 81:
                notices.append('Tabela extensa: primeiras 80 linhas de dados; a cópia inclui todas as linhas analisadas.')
            scroll = Gtk.ScrolledWindow(); scroll.add_css_class('md-table-scroll')
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER); scroll.set_propagate_natural_width(False); scroll.set_min_content_width(0); scroll.set_min_content_height(0); scroll.set_propagate_natural_height(True); scroll.set_child(grid)
            group.append(scroll); target.append(group)
    try:
        blocks(document.root.children, root)
    except RenderLimit:
        notices.append('Limite de componentes atingido. Copie a mensagem completa para conferir o restante.')
    if notices:
        hint = Gtk.Label(label='\n'.join(dict.fromkeys(notices)), xalign=0, wrap=True); hint.add_css_class('dim-label'); root.append(hint)
        root.append(copy_button('Copiar mensagem completa', document.original)) if budget['count'] < MAX_WIDGETS else root.append(_unbudgeted_copy(Gtk, document.original, on_copy))
    root.markdown_notices = notices
    return root


def _unbudgeted_copy(Gtk, text, on_copy):
    button = Gtk.Button(label='Copiar mensagem completa')
    button.connect('clicked', lambda *_: on_copy(display_text(text)))
    return button
