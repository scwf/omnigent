"""Tests for omnigent.tools.builtins.read_skill_file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omnigent.spec.types import SkillSpec
from omnigent.tools.base import ToolContext
from omnigent.tools.builtins import ReadSkillFileTool


@pytest.fixture()
def skill_with_resources(tmp_path: Path) -> SkillSpec:
    """
    A skill with a ``references/`` directory containing a
    file, for testing ``read_skill_file``.

    :returns: A ``SkillSpec`` pointing at a real directory
        with a reference file.
    """
    skill_dir = tmp_path / "skills" / "code-review"
    skill_dir.mkdir(parents=True)
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "style-guide.md").write_text("# Style Guide\n\nUse snake_case.")
    return SkillSpec(
        name="code-review",
        description="Reviews code.",
        content="Review the code.",
        skill_dir=skill_dir,
    )


@pytest.fixture()
def skill_no_resources() -> SkillSpec:
    """
    A skill with no ``skill_dir`` (in-memory only).

    :returns: A ``SkillSpec`` with ``skill_dir=None``.
    """
    return SkillSpec(
        name="summarize",
        description="Summarizes text.",
        content="Summarize the input concisely.",
    )


def test_read_skill_file_returns_content(
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    ReadSkillFileTool.invoke reads a file from the skill dir.
    """
    tool = ReadSkillFileTool([skill_with_resources])
    result = tool.invoke(
        json.dumps(
            {
                "skill_name": "code-review",
                "path": "references/style-guide.md",
            }
        ),
        tool_ctx,
    )
    assert "# Style Guide" in result
    assert "snake_case" in result


def test_read_skill_file_reads_resources_as_utf8(
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skill resources use UTF-8 rather than the Windows locale encoding."""
    assert skill_with_resources.skill_dir is not None
    resource = skill_with_resources.skill_dir / "references" / "utf8.md"
    resource.write_bytes("# 设计说明\n\nUse plans — then execute. ✓".encode())

    original_read_text = Path.read_text
    observed_encoding: str | None = None

    def _record_encoding(path: Path, *args: Any, **kwargs: Any) -> str:
        nonlocal observed_encoding
        if path == resource:
            observed_encoding = kwargs.get("encoding")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _record_encoding)
    tool = ReadSkillFileTool([skill_with_resources])

    result = tool.invoke(
        json.dumps(
            {
                "skill_name": "code-review",
                "path": "references/utf8.md",
            }
        ),
        tool_ctx,
    )

    assert observed_encoding == "utf-8"
    assert "设计说明" in result
    assert "plans — then execute. ✓" in result


def test_read_skill_file_unknown_skill(
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    ReadSkillFileTool.invoke returns error for unknown skill.
    """
    tool = ReadSkillFileTool([skill_with_resources])
    result = tool.invoke(
        json.dumps(
            {
                "skill_name": "nonexistent",
                "path": "references/style-guide.md",
            }
        ),
        tool_ctx,
    )
    assert "not found" in result
    assert "code-review" in result


def test_read_skill_file_traversal_blocked(
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    ReadSkillFileTool.invoke rejects path traversal attempts.
    """
    tool = ReadSkillFileTool([skill_with_resources])
    result = tool.invoke(
        json.dumps(
            {
                "skill_name": "code-review",
                "path": "../../etc/passwd",
            }
        ),
        tool_ctx,
    )
    assert "traversal not allowed" in result


def test_read_skill_file_absolute_path_blocked(
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    ReadSkillFileTool.invoke rejects absolute paths.
    """
    tool = ReadSkillFileTool([skill_with_resources])
    result = tool.invoke(
        json.dumps(
            {
                "skill_name": "code-review",
                "path": "/etc/passwd",
            }
        ),
        tool_ctx,
    )
    assert "path must be relative" in result


def test_read_skill_file_not_found(
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    ReadSkillFileTool.invoke returns error for missing files.
    """
    tool = ReadSkillFileTool([skill_with_resources])
    result = tool.invoke(
        json.dumps(
            {
                "skill_name": "code-review",
                "path": "references/nonexistent.md",
            }
        ),
        tool_ctx,
    )
    assert "file not found" in result


def test_read_skill_file_no_skill_dir(
    skill_no_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    ReadSkillFileTool.invoke returns error when skill has no
    directory on disk.
    """
    tool = ReadSkillFileTool([skill_no_resources])
    result = tool.invoke(
        json.dumps(
            {
                "skill_name": "summarize",
                "path": "references/foo.md",
            }
        ),
        tool_ctx,
    )
    assert "no directory on disk" in result


def test_read_skill_file_missing_arguments(
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    ReadSkillFileTool.invoke returns error when required
    arguments are missing.
    """
    tool = ReadSkillFileTool([skill_with_resources])

    result_no_name = tool.invoke(
        json.dumps({"path": "references/style-guide.md"}),
        tool_ctx,
    )
    assert "missing required 'skill_name'" in result_no_name

    result_no_path = tool.invoke(
        json.dumps({"skill_name": "code-review"}),
        tool_ctx,
    )
    assert "missing required 'path'" in result_no_path


@pytest.mark.parametrize("arguments", ["not-json", "[]"])
def test_read_skill_file_rejects_invalid_arguments(
    arguments: str,
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    Malformed or non-object arguments return an error string.
    """
    tool = ReadSkillFileTool([skill_with_resources])
    result = tool.invoke(arguments, tool_ctx)

    assert result.startswith("Error:")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"skill_name": 123, "path": "references/style-guide.md"},
            "Error: 'skill_name' must be a string",
        ),
        (
            {"skill_name": "code-review", "path": 123},
            "Error: 'path' must be a string",
        ),
    ],
)
def test_read_skill_file_rejects_non_string_arguments(
    payload: dict[str, object],
    expected: str,
    skill_with_resources: SkillSpec,
    tool_ctx: ToolContext,
) -> None:
    """
    Resource lookup fields must be strings before path handling.
    """
    tool = ReadSkillFileTool([skill_with_resources])
    result = tool.invoke(json.dumps(payload), tool_ctx)

    assert result == expected
