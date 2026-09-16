from __future__ import annotations

from uboundai_gtm.cli import build_parser


def test_audit_query_flag_is_repeatable_and_collected_into_a_list():
    parser = build_parser()
    args = parser.parse_args([
        "audit", "--domain", "northstarlabs.ai", "--brand", "North Star Labs",
        "--category", "network detection and response",
        "--query", "Best NDR vendors for critical infrastructure?",
        "--query", "Top signature-independent network sensing tools?",
    ])
    assert args.query == [
        "Best NDR vendors for critical infrastructure?",
        "Top signature-independent network sensing tools?",
    ]


def test_audit_query_flag_defaults_to_none_when_omitted():
    parser = build_parser()
    args = parser.parse_args(["audit", "--domain", "a.com", "--brand", "A", "--category", "widgets"])
    assert args.query is None
