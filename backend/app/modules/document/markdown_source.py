from dataclasses import dataclass
import re
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.tokens import AliasToken, AnchorToken, TagToken

from app.modules.document.schemas import LetterMetadata


MAX_MARKDOWN_CHARACTERS = 120_000
MAX_FRONT_MATTER_CHARACTERS = 16_000
FRONT_MATTER_PATTERN = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class ParsedLetter:
    metadata: LetterMetadata
    body: str


class InvalidMarkdownSource(ValueError):
    pass


class UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def parse_markdown_source(source: str) -> ParsedLetter:
    if len(source) > MAX_MARKDOWN_CHARACTERS:
        raise InvalidMarkdownSource("Markdown source exceeds the size limit")
    match = FRONT_MATTER_PATTERN.match(source)
    if match is None:
        raise InvalidMarkdownSource("Markdown front matter is required")

    raw_front_matter = match.group(1)
    if len(raw_front_matter) > MAX_FRONT_MATTER_CHARACTERS:
        raise InvalidMarkdownSource("Markdown metadata exceeds the size limit")
    try:
        tokens = list(yaml.scan(raw_front_matter, Loader=UniqueKeySafeLoader))
        if len(tokens) > 300:
            raise InvalidMarkdownSource("Markdown metadata contains too many YAML nodes")
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken))
            for token in tokens
        ):
            raise InvalidMarkdownSource("YAML aliases, anchors, and custom tags are unsupported")
        values: Any = yaml.load(raw_front_matter, Loader=UniqueKeySafeLoader)
        metadata = LetterMetadata.model_validate(values)
    except (yaml.YAMLError, ValidationError, RecursionError, TypeError) as error:
        raise InvalidMarkdownSource("Markdown metadata is invalid") from error

    body = source[match.end() :].replace("\r\n", "\n").replace("\r", "\n")
    body = body.strip()
    if not body:
        raise InvalidMarkdownSource("Markdown body cannot be empty")
    return ParsedLetter(metadata=metadata, body=body)
