from __future__ import annotations

from core.models import Detector


def create_default_detectors() -> list[Detector]:
    """Create the default static detector set used by scan entry points."""
    from detectors.semantic_similarity import SemanticSimilarityDetector
    from detectors.obfuscation.encoded_payload import EncodedPayloadDetector
    from detectors.obfuscation.homoglyph import HomoglyphDetector
    from detectors.obfuscation.html_comment import HtmlCommentDetector
    from detectors.obfuscation.unicode_obfuscation import UnicodeObfuscationDetector
    from detectors.tool_poisoning.cross_tool_instruction import CrossToolInstructionDetector
    from detectors.tool_poisoning.hidden_instruction import HiddenInstructionDetector
    from detectors.tool_poisoning.markdown_hidden_link import MarkdownHiddenLinkDetector
    from detectors.tool_poisoning.metadata_poisoning import MetadataPoisoningDetector
    from detectors.tool_poisoning.schema_poisoning import SchemaPoisoningDetector

    return [
        HiddenInstructionDetector(),
        SchemaPoisoningDetector(),
        MetadataPoisoningDetector(),
        CrossToolInstructionDetector(),
        MarkdownHiddenLinkDetector(),
        UnicodeObfuscationDetector(),
        EncodedPayloadDetector(),
        HtmlCommentDetector(),
        HomoglyphDetector(),
        SemanticSimilarityDetector(),
    ]
