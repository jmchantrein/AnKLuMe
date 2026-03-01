"""Tests for scripts/web/html.py — HTML string builders."""

from scripts.web.html import (
    _inline,
    card,
    command_block,
    nav_bar,
    page_wrap,
    render_markdown,
)


class TestPageWrap:
    def test_produces_valid_html(self):
        result = page_wrap("Test", "<p>hello</p>")
        assert "<!DOCTYPE html>" in result
        assert "<title>Test</title>" in result
        assert "</html>" in result

    def test_includes_htmx_cdn(self):
        result = page_wrap("T", "")
        assert "htmx.org" in result

    def test_includes_base_css(self):
        result = page_wrap("T", "")
        assert ":root" in result

    def test_xterm_flag_adds_scripts(self):
        result = page_wrap("T", "", xterm=True)
        assert "xterm.js" in result
        assert "addon-fit" in result
        assert "addon-attach" in result
        assert "xterm.css" in result

    def test_xterm_false_no_scripts(self):
        result = page_wrap("T", "")
        assert "xterm.js" not in result
        assert "addon-fit" not in result

    def test_extra_css_included(self):
        result = page_wrap("T", "", extra_css=".custom{color:red}")
        assert ".custom" in result

    def test_extra_js_included(self):
        result = page_wrap("T", "", extra_js="<script>alert(1)</script>")
        assert "alert(1)" in result

    def test_title_is_html_escaped(self):
        result = page_wrap("<script>xss</script>", "")
        assert "&lt;script&gt;xss&lt;/script&gt;" in result
        assert "<title><script>" not in result

    def test_body_is_embedded_raw(self):
        """Body is raw HTML — caller is responsible for escaping."""
        result = page_wrap("T", "<div>raw</div>")
        assert "<div>raw</div>" in result

    def test_has_charset_meta(self):
        result = page_wrap("T", "")
        assert 'charset="utf-8"' in result

    def test_has_lang_attribute(self):
        result = page_wrap("T", "")
        assert 'lang="en"' in result

    def test_empty_extra_css_still_works(self):
        result = page_wrap("T", "", extra_css="")
        assert "<!DOCTYPE html>" in result

    def test_empty_body(self):
        result = page_wrap("T", "")
        assert "</body>" in result


class TestCard:
    def test_basic_card(self):
        result = card("Title", "Content")
        assert "Title" in result
        assert "Content" in result
        assert 'class="card"' in result

    def test_border_color(self):
        result = card("T", "C", border_color="#ff0000")
        assert "#ff0000" in result
        assert "border-left" in result

    def test_no_border_color(self):
        result = card("T", "C")
        assert "style=" not in result

    def test_title_is_html_escaped(self):
        result = card("<img onerror=alert(1)>", "safe")
        assert "&lt;img" in result
        assert "onerror" not in result.split("&")[0]

    def test_content_is_html_escaped(self):
        result = card("safe", "<script>alert('xss')</script>")
        assert "&lt;script&gt;" in result
        assert "<script>alert" not in result

    def test_border_color_is_html_escaped(self):
        result = card("T", "C", border_color='"><script>alert(1)</script>')
        assert "&lt;script&gt;" in result or "&quot;" in result

    def test_has_h3_tag(self):
        result = card("Title", "Body")
        assert "<h3>" in result
        assert "</h3>" in result


class TestCommandBlock:
    def test_non_clickable_shows_pre(self):
        result = command_block("ls -la")
        assert "<pre" in result
        assert "ls -la" in result
        assert "runCmd" not in result

    def test_non_clickable_has_dollar_prompt(self):
        result = command_block("ls")
        assert "$ ls" in result

    def test_clickable_has_run_button(self):
        result = command_block("incus list", clickable=True)
        assert "runCmd" in result
        assert "incus list" in result
        assert "run-btn" in result

    def test_clickable_has_play_symbol(self):
        result = command_block("ls", clickable=True)
        assert "&#9654;" in result

    def test_escapes_html_in_non_clickable(self):
        result = command_block("echo '<br>'")
        assert "&lt;br&gt;" in result

    def test_escapes_html_in_clickable(self):
        result = command_block("echo '<script>'", clickable=True)
        assert "&lt;script&gt;" in result

    def test_empty_command(self):
        result = command_block("")
        assert "<pre" in result

    def test_command_with_quotes(self):
        result = command_block("echo 'hello world'", clickable=True)
        assert "hello world" in result

    def test_command_with_ampersand(self):
        result = command_block("a & b")
        assert "&amp;" in result


class TestNavBar:
    def test_renders_links(self):
        result = nav_bar([("Home", "/"), ("Guide", "/guide")])
        assert 'href="/"' in result
        assert 'href="/guide"' in result
        assert "Home" in result

    def test_empty_list(self):
        result = nav_bar([])
        assert '<div class="nav">' in result
        assert "</div>" in result

    def test_single_item(self):
        result = nav_bar([("Back", "/back")])
        assert 'href="/back"' in result
        assert "Back" in result

    def test_label_is_html_escaped(self):
        result = nav_bar([("<b>XSS</b>", "/link")])
        assert "&lt;b&gt;" in result

    def test_three_items(self):
        items = [("A", "/a"), ("B", "/b"), ("C", "/c")]
        result = nav_bar(items)
        assert result.count("<a ") == 3


class TestRenderMarkdown:
    def test_heading_h1(self):
        result = render_markdown("# Title")
        assert "<h1>Title</h1>" in result

    def test_heading_h2(self):
        result = render_markdown("## Subtitle")
        assert "<h2>Subtitle</h2>" in result

    def test_heading_h3(self):
        result = render_markdown("### Third")
        assert "<h3>Third</h3>" in result

    def test_code_block(self):
        result = render_markdown("```\necho hello\n```")
        assert "<pre" in result
        assert "echo hello" in result
        assert "</code></pre>" in result

    def test_code_block_escapes_html(self):
        result = render_markdown("```\n<script>alert(1)</script>\n```")
        assert "&lt;script&gt;" in result

    def test_unclosed_code_block(self):
        result = render_markdown("```\ncode here")
        assert "<pre" in result
        assert "code here" in result
        assert "</code></pre>" in result

    def test_list_items_dash(self):
        result = render_markdown("- item one\n- item two")
        assert "<li>" in result
        assert "item one" in result
        assert "item two" in result

    def test_list_items_asterisk(self):
        result = render_markdown("* item one\n* item two")
        assert "<li>" in result
        assert "item one" in result

    def test_bold(self):
        result = render_markdown("This is **bold** text")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        result = render_markdown("This is *italic* text")
        assert "<em>italic</em>" in result

    def test_inline_code(self):
        result = render_markdown("Use `incus list` command")
        assert "<code>incus list</code>" in result

    def test_paragraph(self):
        result = render_markdown("Normal text here")
        assert "<p>Normal text here</p>" in result

    def test_empty_line_preserved(self):
        result = render_markdown("line one\n\nline two")
        lines = result.split("\n")
        assert any(line == "" for line in lines)

    def test_heading_escapes_html(self):
        result = render_markdown("# <script>xss</script>")
        assert "&lt;script&gt;" in result

    def test_empty_string(self):
        result = render_markdown("")
        assert result == ""

    def test_mixed_content(self):
        md = "# Title\n\nSome **bold** text\n\n- item\n\n```\ncode\n```"
        result = render_markdown(md)
        assert "<h1>Title</h1>" in result
        assert "<strong>bold</strong>" in result
        assert "<li>" in result
        assert "<pre" in result


class TestInline:
    def test_bold(self):
        assert "<strong>word</strong>" in _inline("**word**")

    def test_code(self):
        assert "<code>cmd</code>" in _inline("`cmd`")

    def test_italic(self):
        assert "<em>word</em>" in _inline("*word*")

    def test_escapes_html_first(self):
        result = _inline("<b>raw</b>")
        assert "&lt;b&gt;" in result

    def test_plain_text(self):
        assert _inline("hello") == "hello"

    def test_mixed(self):
        result = _inline("Use **bold** and `code` here")
        assert "<strong>bold</strong>" in result
        assert "<code>code</code>" in result
