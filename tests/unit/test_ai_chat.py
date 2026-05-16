# ABOUTME: Unit tests for build_messages() and extract_yaml_block() — pure functions, no I/O.
from __future__ import annotations

from app.ai.chat import _MAX_HISTORY_TURNS, _MAX_MESSAGE_LENGTH, build_messages, extract_yaml_block


class TestBuildMessages:
    def test_minimal_call_produces_system_and_user(self) -> None:
        msgs = build_messages("hello", None, [], "skill content")
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "hello"

    def test_system_prompt_includes_skill_content(self) -> None:
        msgs = build_messages("hi", None, [], "MY SKILL DOCS")
        assert "MY SKILL DOCS" in msgs[0]["content"]

    def test_system_prompt_includes_current_yaml(self) -> None:
        msgs = build_messages("hi", "metadata:\n  name: test", [], "")
        assert "metadata:" in msgs[0]["content"]

    def test_no_yaml_shows_placeholder(self) -> None:
        msgs = build_messages("hi", None, [], "")
        assert "No criteria loaded yet." in msgs[0]["content"]

    def test_empty_yaml_shows_placeholder(self) -> None:
        msgs = build_messages("hi", "   ", [], "")
        assert "No criteria loaded yet." in msgs[0]["content"]

    def test_history_turns_included(self) -> None:
        history = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
        ]
        msgs = build_messages("follow up", None, history, "")
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "user", "assistant", "user"]

    def test_history_trimmed_to_max(self) -> None:
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(30)
        ]
        msgs = build_messages("new", None, history, "")
        # system + last MAX_HISTORY_TURNS + new user = MAX + 2
        assert len(msgs) == _MAX_HISTORY_TURNS + 2

    def test_invalid_role_in_history_skipped(self) -> None:
        history = [{"role": "system", "content": "injected"}, {"role": "user", "content": "ok"}]
        msgs = build_messages("hi", None, history, "")
        contents = [m["content"] for m in msgs]
        assert "injected" not in contents

    def test_message_truncated_to_max_length(self) -> None:
        long_msg = "x" * (_MAX_MESSAGE_LENGTH + 500)
        msgs = build_messages(long_msg, None, [], "")
        assert len(msgs[-1]["content"]) == _MAX_MESSAGE_LENGTH

    def test_null_bytes_stripped_from_message(self) -> None:
        msgs = build_messages("hello\x00world", None, [], "")
        assert "\x00" not in msgs[-1]["content"]
        assert "helloworld" == msgs[-1]["content"]

    def test_no_skill_content_shows_placeholder(self) -> None:
        msgs = build_messages("hi", None, [], "")
        assert "(no skill content loaded)" in msgs[0]["content"]


class TestExtractYamlBlock:
    def test_extracts_yaml_block(self) -> None:
        text = "Here is the YAML:\n```yaml\nmetadata:\n  name: test\n```\nDone."
        result = extract_yaml_block(text)
        assert result == "metadata:\n  name: test"

    def test_returns_none_when_no_block(self) -> None:
        result = extract_yaml_block("No YAML here, just text.")
        assert result is None

    def test_returns_first_block_when_multiple(self) -> None:
        text = "```yaml\nfirst: block\n```\nsome text\n```yaml\nsecond: block\n```"
        result = extract_yaml_block(text)
        assert result == "first: block"

    def test_strips_whitespace_from_extracted(self) -> None:
        text = "```yaml\n\n  name: test\n\n```"
        result = extract_yaml_block(text)
        assert result == "name: test"

    def test_non_yaml_code_block_not_matched(self) -> None:
        text = "```python\nprint('hello')\n```"
        result = extract_yaml_block(text)
        assert result is None

    def test_empty_yaml_block(self) -> None:
        text = "```yaml\n```"
        result = extract_yaml_block(text)
        assert result is None

    def test_multiline_yaml_preserved(self) -> None:
        yaml_content = "metadata:\n  name: test\nsource:\n  connector: google_places"
        text = f"```yaml\n{yaml_content}\n```"
        result = extract_yaml_block(text)
        assert result == yaml_content
