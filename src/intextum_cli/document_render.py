"""A readable, isolated HTML view of a cached DoclingDocument."""

from __future__ import annotations

import html
import re


def render_document(data: dict) -> str:
    import nh3
    from docling_core.transforms.serializer.html import HTMLDocSerializer, HTMLParams
    from docling_core.types.doc import (
        ContentLayer,
        DocItem,
        DoclingDocument,
        ImageRefMode,
    )

    class ReviewSerializer(HTMLDocSerializer):
        def serialize(self, *, item=None, **kwargs):
            result = super().serialize(item=item, **kwargs)
            if isinstance(item, DocItem) and result.text:
                reference = html.escape(item.self_ref, quote=True)
                body = re.sub(
                    r"^(\s*<[a-zA-Z][\w-]*)",
                    lambda match: f'{match[1]} data-doc-ref="{reference}"',
                    result.text,
                    count=1,
                )
                return result.model_copy(update={"text": body})
            return result

    document = DoclingDocument.model_validate(data)
    serialized = (
        ReviewSerializer(
            doc=document,
            params=HTMLParams(
                image_mode=ImageRefMode.REFERENCED,
                include_hyperlinks=False,
                formula_to_mathml=False,
                layers=set(ContentLayer),
                traverse_pictures=True,
            ),
        )
        .serialize()
        .text
    )
    body_match = re.search(r"<body[^>]*>([\s\S]*)</body>", serialized)
    serialized = body_match[1] if body_match else serialized

    def attribute(tag, name, value):
        if tag == "img" and name == "src":
            return (
                value
                if re.fullmatch(
                    r"/api/document/assets/[a-f0-9]{64}/[a-f0-9]{64}\.png", value
                )
                else None
            )
        return value

    body = nh3.clean(
        serialized,
        tags={
            "p",
            "div",
            "span",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "ul",
            "ol",
            "li",
            "table",
            "thead",
            "tbody",
            "tfoot",
            "tr",
            "th",
            "td",
            "caption",
            "figure",
            "figcaption",
            "img",
            "strong",
            "em",
            "u",
            "del",
            "sup",
            "sub",
            "pre",
            "code",
            "blockquote",
            "br",
            "hr",
        },
        attributes={
            "*": {"class", "dir", "data-doc-ref"},
            "img": {"src", "alt"},
            "td": {"rowspan", "colspan"},
            "th": {"rowspan", "colspan", "scope"},
            "ol": {"start"},
            "li": {"value"},
        },
        clean_content_tags={"script", "style", "iframe", "object", "svg"},
        attribute_filter=attribute,
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="stylesheet" href="/document.css"></head>'
        f'<body class="document-content">{body}</body></html>'
    )
