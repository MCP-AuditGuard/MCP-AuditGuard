from __future__ import annotations

from detectors.semantic_similarity import SemanticSimilarityDetector
from detectors.obfuscation.encoded_payload import EncodedPayloadDetector
from detectors.obfuscation.homoglyph import HomoglyphDetector
from detectors.obfuscation.html_comment import HtmlCommentDetector
from detectors.obfuscation.unicode_obfuscation import UnicodeObfuscationDetector
from detectors.registry import create_default_detectors
from detectors.tool_poisoning.cross_tool_instruction import CrossToolInstructionDetector
from detectors.tool_poisoning.hidden_instruction import HiddenInstructionDetector
from detectors.tool_poisoning.markdown_hidden_link import MarkdownHiddenLinkDetector
from detectors.tool_poisoning.metadata_poisoning import MetadataPoisoningDetector
from detectors.tool_poisoning.obfuscated_hidden_instruction import (
    ObfuscatedHiddenInstructionDetector,
)
from detectors.tool_poisoning.schema_poisoning import SchemaPoisoningDetector


EXPECTED_DETECTOR_CLASSES = [
    UnicodeObfuscationDetector,
    EncodedPayloadDetector,
    HtmlCommentDetector,
    HomoglyphDetector,
    ObfuscatedHiddenInstructionDetector,
    HiddenInstructionDetector,
    SchemaPoisoningDetector,
    MetadataPoisoningDetector,
    CrossToolInstructionDetector,
    MarkdownHiddenLinkDetector,
    SemanticSimilarityDetector,
]


def test_create_default_detectors_returns_expected_static_detectors() -> None:
    detectors = create_default_detectors()
    detector_classes = [detector.__class__ for detector in detectors]

    assert isinstance(detectors, list)
    assert len(detectors) == len(EXPECTED_DETECTOR_CLASSES)
    assert detector_classes == EXPECTED_DETECTOR_CLASSES

    for detector_class in EXPECTED_DETECTOR_CLASSES:
        assert detector_classes.count(detector_class) == 1


def test_create_default_detectors_returns_new_instances_each_call() -> None:
    first_detectors = create_default_detectors()
    second_detectors = create_default_detectors()

    assert [detector.__class__ for detector in first_detectors] == [
        detector.__class__ for detector in second_detectors
    ]
    assert all(
        first_detector is not second_detector
        for first_detector, second_detector in zip(first_detectors, second_detectors, strict=True)
    )
