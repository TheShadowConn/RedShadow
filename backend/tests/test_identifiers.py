"""Identifier normalisation, kind detection and cell splitting (pure functions, no database)."""

import pytest

from apps.organisations import identifiers as ident


@pytest.mark.parametrize(
    "kind,raw,normalized",
    [
        ("ip", " 10.0.0.5 ", "10.0.0.5"),
        ("ip", "2001:0DB8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        ("ip", "[::1]", "::1"),
        ("cidr", "10.0.0.7/24", "10.0.0.0/24"),
        ("hostname", "WEB01.Acme.Test.", "web01.acme.test"),
        ("domain", "Acme.TEST", "acme.test"),
        ("domain", "bücher.example", "xn--bcher-kva.example"),
        ("url", "HTTPS://Shop.Acme.Test:443/App/?a=1#frag", "https://shop.acme.test/App?a=1"),
        ("url", "http://shop.acme.test:8080/", "http://shop.acme.test:8080"),
        ("mac", "00-1A-2B-3C-4D-5E", "00:1a:2b:3c:4d:5e"),
        ("mac", "001a.2b3c.4d5e", "00:1a:2b:3c:4d:5e"),
        ("repo", "HTTPS://GitHub.com/Acme/Shop.git/", "https://github.com/Acme/Shop".lower()),
        ("cloud_id", "arn:aws:s3:::Acme-Bucket", "arn:aws:s3:::Acme-Bucket"),
        ("other", "  Some   Thing ", "some thing"),
    ],
)
def test_normalize(kind, raw, normalized):
    assert ident.normalize(kind, raw).normalized == normalized


@pytest.mark.parametrize(
    "kind,raw",
    [
        ("ip", "10.0.0.256"),
        ("ip", "web01"),
        ("cidr", "10.0.0.0/33"),
        ("hostname", "bad host"),
        ("hostname", "-bad.example"),
        ("domain", "a" * 64 + ".example"),
        ("url", "shop.acme.test"),
        ("url", "javascript://x"),
        ("url", "https://user:secret@acme.test/"),
        ("url", "https:///nohost"),
        ("mac", "00:1a:2b"),
        ("mac", "zz:1a:2b:3c:4d:5e"),
        ("ip", ""),
        ("ip", "1\x00.2.3.4"),
        ("other", "x" * 501),
        ("nonsense", "x"),
    ],
)
def test_normalize_rejects(kind, raw):
    with pytest.raises(ident.IdentifierError):
        ident.normalize(kind, raw)


def test_hostname_and_domain_share_one_match_key_but_other_kinds_do_not():
    assert (
        ident.normalize("hostname", "Web.Acme.Test").match_key == ident.normalize("domain", "web.acme.test").match_key
    )
    assert ident.normalize("ip", "10.0.0.5").match_key != ident.normalize("other", "10.0.0.5").match_key
    assert ident.normalize("url", "http://a.test").match_key != ident.normalize("url", "https://a.test").match_key


def test_spellings_of_one_identifier_collide():
    a = ident.normalize("url", "https://Shop.Acme.test/")
    b = ident.normalize("url", "https://shop.acme.test:443")
    assert a.match_key == b.match_key


@pytest.mark.parametrize(
    "raw,kind",
    [
        ("10.0.0.5", "ip"),
        ("fe80::1", "ip"),
        ("10.0.0.0/24", "cidr"),
        ("00:1a:2b:3c:4d:5e", "mac"),
        ("https://shop.acme.test/x", "url"),
        ("arn:aws:iam::123456789012:root", "cloud_id"),
        ("web01.acme.test", "hostname"),
        ("web01", "hostname"),
        ("not a thing!", "other"),
        ("", "other"),
    ],
)
def test_detect_kind(raw, kind):
    assert ident.detect_kind(raw) == kind


def test_parse_detects_when_no_kind_is_given():
    assert ident.parse("10.0.0.5").kind == "ip"
    assert ident.parse("10.0.0.5", "other").kind == "other"


def test_split_cell_keeps_commas_inside_urls():
    assert ident.split_cell("10.0.0.1; 10.0.0.2,10.0.0.3\n10.0.0.4|10.0.0.5") == [
        "10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5",
    ]  # fmt: skip
    assert ident.split_cell("https://a.test/?x=1,2; https://b.test") == ["https://a.test/?x=1,2", "https://b.test"]
    assert ident.split_cell("") == []
